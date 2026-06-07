"""
Response Generator — task2_!!!! Rewrite

Citation-grounded, adaptive-format response generator. Replaces the
previous monolithic generator with structured citation anchors, adaptive
depth formatting, and post-processing to extract which sources were cited.

Key features:
- Numbered [1], [2] citation anchors in LLM output
- Adaptive formatting: concise for simple, structured for complex
- Post-processing to build verified source manifest
- Multi-turn conversation context support
- JSON leak protection preserved from previous version
"""
import logging
import re
from typing import List, Dict, Any, Optional, AsyncGenerator

from backend.core.config import get_settings
from backend.core.llm_client import LLMClient
from backend.query.retriever import RetrievalResult
from backend.query.resolution import (
    CitedSource,
    ResponseTier,
    VerifiedChunk,
    VerifiedContext,
)
from backend.observability.telemetry import tracer

settings = get_settings()
logger = logging.getLogger(__name__)


class Answer:
    """Response container with structured citations."""

    def __init__(
        self,
        answer_text: str,
        sources: List[Dict[str, str]],
        citations: List[CitedSource] = None,
        citations_used: List[int] = None,
        tokens_used: int = 0,
        grounding_score: float = 0.0,
        response_tier: str = ResponseTier.FAST_RAG.value,
        disclaimer: Optional[str] = None,
        faithfulness_score: float = 1.0,
        relevance_score: float = 1.0,
        eval_reasoning: str = "",
        user_profile: Optional[Dict[str, Any]] = None,
    ):
        self.answer_text = answer_text
        self.sources = sources
        self.citations = citations or []
        self.citations_used = citations_used or []
        self.tokens_used = tokens_used
        self.grounding_score = grounding_score
        self.response_tier = response_tier
        self.disclaimer = disclaimer
        self.faithfulness_score = faithfulness_score
        self.relevance_score = relevance_score
        self.eval_reasoning = eval_reasoning
        self.user_profile = user_profile



# ─── Format instruction templates ──────────────────────────────

_FORMAT_CONCISE = (
    "RESPONSE FORMAT: Give a direct, concise answer in 1-4 sentences. "
    "Use inline citations like [1] to reference sources. "
    "Keep it simple and easy to understand."
)

_FORMAT_STANDARD = (
    "RESPONSE FORMAT: Provide a clear answer with key points as bullet points. "
    "Use inline citations [1], [2] for each factual claim. "
    "Include a brief explanation after the bullets if needed."
)

_FORMAT_STRUCTURED = (
    "RESPONSE FORMAT: Provide a structured analysis with these sections:\n"
    "## Summary\nA brief executive summary (2-3 sentences)\n\n"
    "## Key Findings\nBulleted key points with inline citations [1], [2]\n\n"
    "## Details\nDetailed explanation with evidence\n\n"
    "## Recommendations\nActionable next steps if applicable"
)


def _get_format_instruction(tier: ResponseTier) -> str:
    """Select the format template based on response tier."""
    if tier == ResponseTier.DIRECT:
        return _FORMAT_CONCISE
    elif tier == ResponseTier.FAST_RAG:
        return _FORMAT_STANDARD
    elif tier in (ResponseTier.FULL_SWARM, ResponseTier.TOOL_EXEC):
        return _FORMAT_STRUCTURED
    return _FORMAT_STANDARD


def _max_output_tokens_for_tier(tier: ResponseTier) -> int:
    if tier == ResponseTier.DIRECT:
        return 128
    if tier == ResponseTier.FAST_RAG:
        return 256
    if tier in (ResponseTier.FULL_SWARM, ResponseTier.TOOL_EXEC):
        return 384
    return 256


# ─── Citation builder ──────────────────────────────────────────

def build_citation_manifest(
    chunks: List[VerifiedChunk] = None,
    retrieval_results: List[RetrievalResult] = None,
) -> tuple[str, List[CitedSource]]:
    """
    Build numbered citation anchors and a CitedSource list.

    Returns:
        (context_with_anchors: str, citations: List[CitedSource])
    """
    sources = chunks or []
    citations: List[CitedSource] = []
    context_blocks: List[str] = []

    # Handle VerifiedChunk list
    if chunks:
        for i, chunk in enumerate(chunks):
            cid = i + 1
            label = chunk.title
            if chunk.section_heading:
                label = f"{chunk.title} — {chunk.section_heading}"

            citations.append(CitedSource(
                id=cid,
                title=chunk.title,
                url=chunk.source_url,
                section_heading=chunk.section_heading,
                confidence=chunk.score,
                verified=(chunk.verdict.value == "relevant"),
                chunk_id=chunk.chunk_id,
            ))

            context_blocks.append(
                f"[{cid}] Source: {label}\n"
                f"URL: {chunk.source_url}\n"
                f"Content:\n{chunk.content}"
            )

    # Fallback: handle raw RetrievalResult list
    elif retrieval_results:
        for i, rr in enumerate(retrieval_results):
            cid = i + 1
            heading = None
            if isinstance(rr.metadata.get("heading_path"), list) and rr.metadata["heading_path"]:
                heading = rr.metadata["heading_path"][-1]

            label = rr.title
            if heading:
                label = f"{rr.title} — {heading}"

            citations.append(CitedSource(
                id=cid,
                title=rr.title,
                url=rr.source_url,
                section_heading=heading,
                confidence=rr.score,
                verified=True,
                chunk_id=rr.chunk_id,
            ))

            context_blocks.append(
                f"[{cid}] Source: {label}\n"
                f"URL: {rr.source_url}\n"
                f"Content:\n{rr.content}"
            )

    context_text = "\n\n---\n\n".join(context_blocks)
    return context_text, citations


def extract_citations_used(text: str) -> List[int]:
    """Extract which [N] citation numbers were actually used in the response."""
    return sorted(set(int(m) for m in re.findall(r"\[(\d+)\]", text)))


# ─── Generator class ──────────────────────────────────────────

class Generator:
    """
    Citation-grounded response generator with adaptive formatting.
    """

    def __init__(self):
        self.llm = LLMClient(model_type="smart")

    async def generate_grounded_response(
        self,
        question: str,
        verified_context: VerifiedContext,
        tier: ResponseTier = ResponseTier.FAST_RAG,
        conversation_history: Optional[List[Dict[str, str]]] = None,
    ) -> Answer:
        """
        Primary generation method — uses CRAG-verified chunks with citations.
        """
        logger.info("Generating grounded response (tier=%s) for: %s", tier.value, question[:60])

        chunks = verified_context.verified_chunks
        if not chunks:
            return Answer(
                answer_text=(
                    "I wasn't able to find relevant information in your company's "
                    "knowledge base to answer this question."
                ),
                sources=[],
                grounding_score=0.0,
                response_tier=tier.value,
            )

        # Build citation context
        context_text, citations = build_citation_manifest(chunks=chunks)
        format_instruction = _get_format_instruction(tier)

        # Build source reference for the prompt
        source_ref = "\n".join(
            f"[{c.id}] {c.display_label()} ({c.url})" for c in citations
        )

        # Build system prompt
        system_prompt = (
            "You are Assest, a company knowledge assistant. "
            "Answer the user's question using ONLY the provided context.\n\n"
            "RULES:\n"
            "1. Cite every factual claim using [1], [2] etc. matching the SOURCES list.\n"
            "2. If the context doesn't contain the answer, say: "
            "\"I don't have enough information in the knowledge base to answer this fully.\"\n"
            "3. Never make up information not present in the context.\n"
            "4. When documents conflict, cite both and note the conflict with dates.\n"
            "5. Be professional but conversational — explain things clearly.\n\n"
            f"{format_instruction}\n\n"
            f"SOURCES:\n{source_ref}"
        )

        # Build user prompt with optional conversation history
        user_prompt_parts = []
        if conversation_history:
            history_text = self._format_conversation_history(conversation_history)
            user_prompt_parts.append(
                f"CONVERSATION HISTORY (for context only):\n{history_text}\n---"
            )

        user_prompt_parts.append(
            f"KNOWLEDGE CONTEXT:\n{context_text}\n\n"
            f"QUESTION: {question}"
        )

        user_prompt = "\n\n".join(user_prompt_parts)

        try:
            answer_text = await self.llm.chat_completion(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.1,
                max_tokens=_max_output_tokens_for_tier(tier),
                prompt_cache_key=f"grounded:{tier.value}:v1",
            )

            # JSON leak protection
            answer_text = self._sanitize_output(answer_text, system_prompt, user_prompt)

            # Extract used citations
            used = extract_citations_used(answer_text)

            # Filter sources to only those actually cited
            cited_sources = [c for c in citations if c.id in used]
            legacy_sources = [
                {"title": c.title, "url": c.url} for c in cited_sources
            ]

            # Add disclaimer if low confidence
            disclaimer = None
            if verified_context.confidence_signal == "low":
                disclaimer = (
                    "⚠️ Some of the sources used had lower confidence scores. "
                    "Please verify this information with your team."
                )

            return Answer(
                answer_text=answer_text,
                sources=legacy_sources,
                citations=citations,  # all available citations
                citations_used=used,
                grounding_score=verified_context.grounding_score,
                response_tier=tier.value,
                disclaimer=disclaimer,
            )

        except Exception as e:
            logger.error("Grounded generation failed: %s", e)
            best = chunks[0].content.strip() if chunks else ""
            return Answer(
                answer_text=best[:900] or "I couldn't find this in your company's knowledge base.",
                sources=[{"title": chunks[0].title, "url": chunks[0].source_url}] if chunks else [],
                grounding_score=0.0,
                response_tier=tier.value,
            )

    async def stream_grounded_response(
        self,
        question: str,
        verified_context: VerifiedContext,
        tier: ResponseTier = ResponseTier.FAST_RAG,
        conversation_history: Optional[List[Dict[str, str]]] = None,
    ) -> AsyncGenerator[str, None]:
        """
        Streaming version of generate_grounded_response.
        Yields raw tokens from the LLM.
        """
        logger.info("Streaming grounded response (tier=%s) for: %s", tier.value, question[:60])

        chunks = verified_context.verified_chunks
        if not chunks:
            yield "I wasn't able to find relevant information in your company's knowledge base to answer this question."
            return

        # Build citation context
        context_text, citations = build_citation_manifest(chunks=chunks)
        format_instruction = _get_format_instruction(tier)

        # Build source reference for the prompt
        source_ref = "\n".join(
            f"[{c.id}] {c.display_label()} ({c.url})" for c in citations
        )

        # Build system prompt
        system_prompt = (
            "You are Assest, a company knowledge assistant. "
            "Answer the user's question using ONLY the provided context.\n\n"
            "RULES:\n"
            "1. Cite every factual claim using [1], [2] etc. matching the SOURCES list.\n"
            "2. If the context doesn't contain the answer, say: "
            "\"I don't have enough information in the knowledge base to answer this fully.\"\n"
            "3. Never make up information not present in the context.\n"
            "4. When documents conflict, cite both and note the conflict with dates.\n"
            "5. Be professional but conversational — explain things clearly.\n\n"
            f"{format_instruction}\n\n"
            f"SOURCES:\n{source_ref}"
        )

        # Build user prompt with optional conversation history
        user_prompt_parts = []
        if conversation_history:
            history_text = self._format_conversation_history(conversation_history)
            user_prompt_parts.append(
                f"CONVERSATION HISTORY (for context only):\n{history_text}\n---"
            )

        user_prompt_parts.append(
            f"KNOWLEDGE CONTEXT:\n{context_text}\n\n"
            f"QUESTION: {question}"
        )

        user_prompt = "\n\n".join(user_prompt_parts)

        # Yield tokens from chat_completion_stream
        async for token in self.llm.chat_completion_stream(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.1,
            max_tokens=_max_output_tokens_for_tier(tier),
            prompt_cache_key=f"grounded-stream:{tier.value}:v1",
        ):
            yield token

    async def generate_direct_response(
        self,
        question: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
    ) -> Answer:
        """
        Direct response for conversational/greeting queries (no retrieval).
        """
        logger.info("Generating direct response for: %s", question[:60])

        system_prompt = (
            "You are Assest, a friendly company knowledge assistant. "
            "Respond conversationally and helpfully. Keep it brief. "
            "If the user seems to be asking a knowledge question, suggest "
            "they rephrase it as a specific question."
        )

        user_prompt = question
        if conversation_history:
            history_text = self._format_conversation_history(conversation_history)
            user_prompt = (
                f"CONVERSATION HISTORY:\n{history_text}\n---\n\n"
                f"CURRENT MESSAGE: {question}"
            )

        try:
            answer_text = await self.llm.chat_completion(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.5,
                max_tokens=_max_output_tokens_for_tier(ResponseTier.DIRECT),
                prompt_cache_key="direct:v1",
            )
            return Answer(
                answer_text=answer_text or "Hello! How can I help you today?",
                sources=[],
                response_tier=ResponseTier.DIRECT.value,
            )
        except Exception as e:
            logger.error("Direct generation failed: %s", e)
            return Answer(
                answer_text="Hello! How can I help you today?",
                sources=[],
                response_tier=ResponseTier.DIRECT.value,
            )

    async def generate_with_reasoning_context(self, question: str, context: str) -> Answer:
        """
        Generates answer using structured reasoning context from the swarm.
        Preserved for backward compatibility with ReasoningOrchestrator.
        """
        logger.info("Generating swarm answer for: %s", question[:60])
        with tracer.start_as_current_span("generation.reasoning_context") as span:
            span.set_attribute("question", question[:200])
            span.set_attribute("context_length", len(context))

        system_prompt = (
            "You are the Assest Knowledge Architect. Answer the user's question "
            "using the provided reasoning context. Maintain high precision and "
            "explicitly cite whether information comes from documentation, "
            "the knowledge graph, or the event timeline. "
            "Use professional Markdown formatting with structured sections."
        )

        try:
            answer_text = await self.llm.chat_completion(
                system_prompt=system_prompt,
                user_prompt=f"Question: {question}\n\nREASONING CONTEXT:\n{context}",
                temperature=0,
                max_tokens=_max_output_tokens_for_tier(ResponseTier.FULL_SWARM),
                prompt_cache_key="swarm:v1",
            )
            span.set_attribute("response_length", len(answer_text or ""))
            return Answer(
                answer_text=answer_text,
                sources=[],
                response_tier=ResponseTier.FULL_SWARM.value,
            )
        except Exception as e:
            logger.error("Swarm generation failed: %s", e)
            span.record_exception(e)
            return Answer(answer_text="Error generating answer.", sources=[])

    # ── Legacy compatibility ─────────────────────────────────

    async def generate_answer(self, question: str, chunks: List[RetrievalResult]) -> Answer:
        """
        Legacy method — wraps new grounded generator for backward compatibility.
        """
        context_text, citations = build_citation_manifest(retrieval_results=chunks)

        # Create a minimal VerifiedContext
        verified = VerifiedContext(
            verified_chunks=[
                VerifiedChunk(
                    chunk_id=c.chunk_id,
                    content=c.content,
                    source_url=c.source_url,
                    title=c.title,
                    score=c.score,
                    metadata=c.metadata,
                )
                for c in chunks
            ],
            grounding_score=0.7,
            confidence_signal="medium",
        )

        return await self.generate_grounded_response(
            question=question,
            verified_context=verified,
            tier=ResponseTier.FAST_RAG,
        )

    # ── Private helpers ─────────────────────────────────────

    def _format_conversation_history(
        self, history: List[Dict[str, str]]
    ) -> str:
        """Format conversation history for prompt injection."""
        lines = []
        for msg in history:
            role = msg.get("role", "user").capitalize()
            content = msg.get("content", "")
            # Truncate long previous answers
            if len(content) > 500:
                content = content[:500] + "..."
            lines.append(f"{role}: {content}")
        return "\n".join(lines)

    def _sanitize_output(
        self, text: str, system_prompt: str, user_prompt: str
    ) -> str:
        """JSON leak protection and output sanitization."""
        if not text:
            return ""

        stripped = text.strip()
        if stripped.startswith("{") and ("tasks" in stripped or "plan" in stripped):
            logger.warning("Internal planning leak detected. Re-triggering with strict NL enforcement.")
            return (
                "I found relevant information but encountered a formatting issue. "
                "Please try asking your question again."
            )

        return text
