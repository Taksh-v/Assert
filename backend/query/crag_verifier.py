"""
Corrective-RAG (CRAG) Verification Layer — task2_!!!!

Prevents hallucination by verifying retrieved chunks BEFORE generation.
Scores each chunk as RELEVANT / AMBIGUOUS / IRRELEVANT and filters
accordingly. If all chunks are rejected, signals a knowledge gap with
optional web-search fallback.

Architecture:
    Retriever → CRAG Verifier → (verified chunks) → Generator
                    ↓ (rejected)
              Knowledge Gap Handler → web fallback → retry once → admit gap
"""
import logging
import json
import asyncio
from typing import List, Dict, Any, Optional

from backend.core.llm_client import LLMClient
from backend.core.config import get_settings
from backend.query.retriever import RetrievalResult
from backend.query.resolution import (
    CRAGVerdict,
    VerifiedChunk,
    VerifiedContext,
)

logger = logging.getLogger(__name__)
settings = get_settings()


class CRAGVerifier:
    """
    Corrective-RAG layer that evaluates retrieved chunk relevance
    before passing to the generator. Uses a fast LLM call to score
    each chunk against the user's query.
    """

    # Minimum verified chunks to proceed with generation
    MIN_VERIFIED = 1
    # Score threshold for RELEVANT (0-1 from LLM self-assessment)
    RELEVANCE_THRESHOLD = 0.6

    def __init__(self):
        self.llm = LLMClient(model_type="fast")

    async def verify(
        self,
        question: str,
        chunks: List[RetrievalResult],
        workspace_id: str,
    ) -> VerifiedContext:
        """
        Verify retrieved chunks against the query using a lightweight LLM call.
        Returns a VerifiedContext with verified/rejected chunks and a confidence signal.
        """
        if not chunks:
            return VerifiedContext(
                confidence_signal="none",
                grounding_score=0.0,
                needs_web_fallback=True,
            )

        top_score = max((chunk.score for chunk in chunks), default=0.0)
        if top_score >= getattr(settings, "crag_skip_high_confidence_threshold", 0.82):
            verified = [
                VerifiedChunk(
                    chunk_id=chunk.chunk_id,
                    content=chunk.content,
                    source_url=chunk.source_url,
                    title=chunk.title,
                    section_heading=chunk.metadata.get("heading_path", [None])[-1]
                    if isinstance(chunk.metadata.get("heading_path"), list)
                    and chunk.metadata.get("heading_path")
                    else chunk.metadata.get("section_heading"),
                    score=chunk.score,
                    verdict=CRAGVerdict.RELEVANT,
                    metadata=chunk.metadata,
                )
                for chunk in chunks[: min(3, len(chunks))]
            ]
            grounding_score = min(1.0, top_score)
            return VerifiedContext(
                verified_chunks=verified,
                rejected_chunks=[],
                grounding_score=grounding_score,
                confidence_signal="high",
                needs_web_fallback=False,
            )

        logger.info(
            "CRAG: Verifying %d chunks for query: %s",
            len(chunks),
            question[:60],
        )

        # Score all chunks in parallel using a single batch LLM call
        verdicts = await self._batch_score_relevance(question, chunks)

        verified: List[VerifiedChunk] = []
        rejected: List[VerifiedChunk] = []

        for chunk, verdict in zip(chunks, verdicts):
            vc = VerifiedChunk(
                chunk_id=chunk.chunk_id,
                content=chunk.content,
                source_url=chunk.source_url,
                title=chunk.title,
                section_heading=chunk.metadata.get("heading_path", [None])[-1]
                if isinstance(chunk.metadata.get("heading_path"), list)
                and chunk.metadata.get("heading_path")
                else chunk.metadata.get("section_heading"),
                score=chunk.score,
                verdict=verdict,
                metadata=chunk.metadata,
            )
            if verdict == CRAGVerdict.RELEVANT:
                verified.append(vc)
            elif verdict == CRAGVerdict.AMBIGUOUS:
                # Keep ambiguous but flag them
                verified.append(vc)
            else:
                rejected.append(vc)

        # Calculate grounding confidence
        if verified:
            relevant_count = sum(
                1 for v in verified if v.verdict == CRAGVerdict.RELEVANT
            )
            grounding_score = relevant_count / len(chunks)
        else:
            grounding_score = 0.0

        # Determine confidence signal
        if grounding_score >= 0.6:
            confidence_signal = "high"
        elif grounding_score >= 0.3:
            confidence_signal = "medium"
        elif verified:
            confidence_signal = "low"
        else:
            confidence_signal = "none"

        needs_fallback = len(verified) < self.MIN_VERIFIED

        logger.info(
            "CRAG result: verified=%d, rejected=%d, grounding=%.2f, signal=%s, fallback=%s",
            len(verified),
            len(rejected),
            grounding_score,
            confidence_signal,
            needs_fallback,
        )

        return VerifiedContext(
            verified_chunks=verified,
            rejected_chunks=rejected,
            grounding_score=grounding_score,
            confidence_signal=confidence_signal,
            needs_web_fallback=needs_fallback,
        )

    async def _batch_score_relevance(
        self,
        question: str,
        chunks: List[RetrievalResult],
    ) -> List[CRAGVerdict]:
        """
        Score all chunks in a single LLM call for efficiency.
        Returns a list of CRAGVerdict values, one per chunk.
        """
        # Build a compact representation of each chunk for scoring
        chunk_summaries = []
        for i, chunk in enumerate(chunks):
            preview = chunk.content[:300].replace("\n", " ").strip()
            chunk_summaries.append(f"[{i}] Title: {chunk.title}\nContent: {preview}")

        prompt = f"""You are a relevance judge for a company knowledge base. 
Evaluate each retrieved chunk against the user's question and determine if the chunk 
contains information that helps answer the question.

USER QUESTION: "{question}"

RETRIEVED CHUNKS:
{chr(10).join(chunk_summaries)}

For EACH chunk, classify as:
- "relevant": Contains information that directly helps answer the question
- "ambiguous": Tangentially related but may not directly answer the question
- "irrelevant": Does not help answer the question at all

Output ONLY valid JSON — an array of objects:
[{{"index": 0, "verdict": "relevant"}}, {{"index": 1, "verdict": "irrelevant"}}, ...]
"""
        try:
            response = await self.llm.chat_completion(
                system_prompt="You are a precision relevance judge. Output ONLY valid JSON.",
                user_prompt=prompt,
                temperature=0,
                max_tokens=getattr(settings, "llm_verifier_max_output_tokens", 128),
                prompt_cache_key="crag-verifier:v1",
            )

            # Parse the JSON response
            cleaned = response.strip()
            if "```json" in cleaned:
                cleaned = cleaned.split("```json")[1].split("```")[0].strip()
            elif "```" in cleaned:
                cleaned = cleaned.split("```")[1].split("```")[0].strip()

            scored = json.loads(cleaned)

            # Map back to CRAGVerdict
            verdict_map = {
                "relevant": CRAGVerdict.RELEVANT,
                "ambiguous": CRAGVerdict.AMBIGUOUS,
                "irrelevant": CRAGVerdict.IRRELEVANT,
            }

            verdicts: List[CRAGVerdict] = []
            scored_by_index = {item["index"]: item["verdict"] for item in scored}

            for i in range(len(chunks)):
                raw_verdict = scored_by_index.get(i, "ambiguous")
                verdicts.append(
                    verdict_map.get(raw_verdict, CRAGVerdict.AMBIGUOUS)
                )

            return verdicts

        except Exception as e:
            logger.warning("CRAG batch scoring failed: %s. Assuming all relevant.", e)
            # Fail-open: treat all as relevant if scoring fails
            return [CRAGVerdict.RELEVANT] * len(chunks)


class KnowledgeGapHandler:
    """
    Handles cases where CRAG rejects all chunks.
    Strategy: 1) attempt web search fallback, 2) if that fails, admit gap.
    """

    def __init__(self):
        self.llm = LLMClient(model_type="fast")

    async def handle_gap(
        self,
        question: str,
        workspace_id: str,
    ) -> Dict[str, Any]:
        """
        Attempt web search as fallback. If web search also fails,
        return a graceful knowledge-gap response.
        """
        logger.info("KnowledgeGapHandler: Attempting web fallback for: %s", question[:60])

        # --- Attempt 1: Web search fallback ---
        web_result = await self._web_search_fallback(question)
        if web_result and web_result.get("found"):
            return {
                "answer": web_result["answer"],
                "sources": web_result.get("sources", []),
                "method": "web_search_fallback",
                "grounding_score": 0.4,  # lower confidence for web results
                "disclaimer": (
                    "⚠️ This answer was found via web search, not from your company's "
                    "knowledge base. Please verify the information."
                ),
            }

        # --- Attempt 2: Admit the gap gracefully ---
        logger.info("KnowledgeGapHandler: Web fallback failed. Admitting gap.")
        return {
            "answer": (
                "I wasn't able to find this information in your company's knowledge base. "
                "Here are some suggestions:\n"
                "- Try rephrasing your question with different keywords\n"
                "- Ask your team to add relevant documentation to a connected source\n"
                "- Check if the information exists in a source that hasn't been connected yet"
            ),
            "sources": [],
            "method": "knowledge_gap",
            "grounding_score": 0.0,
            "disclaimer": None,
        }

    async def _web_search_fallback(
        self, question: str
    ) -> Optional[Dict[str, Any]]:
        """
        Lightweight, free web search attempt using DuckDuckGo.
        Requires no API key and runs 100% free.
        """
        try:
            from duckduckgo_search import DDGS
            import asyncio

            def _ddg_sync():
                with DDGS() as ddgs:
                    return list(ddgs.text(question, max_results=4))

            loop = asyncio.get_running_loop()
            results = await loop.run_in_executor(None, _ddg_sync)

            if not results:
                logger.info("DuckDuckGo search returned no results.")
                return None

            snippets = []
            sources = []
            for r in results:
                title = r.get("title", "Web Result")
                url = r.get("href", "#")
                body = r.get("body", "")
                if body:
                    snippets.append(f"Source: {title} ({url})\nContent: {body}")
                    sources.append({"title": title, "url": url})

            if not snippets:
                return None

            context_text = "\n\n".join(snippets)
            prompt = f"""You are a helpful assistant. The company's knowledge base did not contain the answer,
so we searched the web instead. Synthesize a concise answer using the search context below.
If the context does not answer the question, output "NO_ANSWER".

USER QUESTION: "{question}"

WEB SEARCH RESULTS:
{context_text}
"""
            answer = await self.llm.chat_completion(
                system_prompt="You are a factual summarizer. Ground your answer strictly on the provided web results.",
                user_prompt=prompt,
                temperature=0.1,
            )

            if not answer or "NO_ANSWER" in answer.upper():
                return None

            return {
                "found": True,
                "answer": answer,
                "sources": sources,
            }
        except Exception as e:
            logger.warning("DuckDuckGo web fallback failed: %s", e)
            return None
