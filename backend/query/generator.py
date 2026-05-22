import logging
from typing import List, Dict
from backend.core.config import get_settings
from backend.query.retriever import RetrievalResult

settings = get_settings()
logger = logging.getLogger(__name__)


class Answer:
    def __init__(self, answer_text: str, sources: List[Dict[str, str]], tokens_used: int = 0):
        self.answer_text = answer_text
        self.sources = sources
        self.tokens_used = tokens_used


from backend.core.llm_client import LLMClient

class Generator:
    """
    Generates grounded answers from retrieved chunks using the local brain proxy.
    """

    def __init__(self):
        self.llm = LLMClient(model_type="smart")

    async def generate_with_reasoning_context(self, question: str, context: str) -> Answer:
        """
        Layer 12: Generates an answer using the structured reasoning context.
        """
        logger.info(f"Generating Phase 2 answer for: {question}")
        
        system_prompt = (
            "You are the Assest Knowledge Architect. Answer the user's question using the provided reasoning context. "
            "Maintain high precision and explicitly cite whether information comes from documentation, the knowledge graph, or the event timeline. "
            "Use professional Markdown formatting."
        )

        try:
            answer_text = await self.llm.chat_completion(
                system_prompt=system_prompt,
                user_prompt=f"Question: {question}\n\nREASONING CONTEXT:\n{context}",
                temperature=0
            )
            return Answer(answer_text=answer_text, sources=[])
        except Exception as e:
            logger.error(f"P2 LLM generation failed: {e}")
            return Answer(answer_text="Error generating answer.", sources=[])

    async def generate_answer(self, question: str, chunks: List[RetrievalResult]) -> Answer:
        """
        Generate answer based on retrieved chunks.
        """
        logger.info(f"Generating answer for: {question}")
        
        # 1. Construct context
        context = "\n\n".join([f"Source: {c.title} ({c.source_url})\nContent: {c.content}" for c in chunks])
        
        # 2. Define system prompt (Phase 4: Temporal Awareness)
        system_prompt = (
            "You are the Assest knowledge assistant. Answer ONLY based on the provided knowledge chunks. "
            "IMPORTANT: Pay close attention to document dates/times. Newer documents override older ones. "
            "If you find a conflict between an older document and a newer one, prioritize the newer information "
            "and explicitly mention that a conflict was detected (e.g. 'The 2024 policy contradicts the 2022 version; the current rule is...'). "
            "Always cite the source document and its date for each claim. Use Markdown formatting."
        )
        
        sources = []
        seen_sources = set()
        for chunk in chunks:
            key = (chunk.title, chunk.source_url)
            if key not in seen_sources:
                sources.append({"title": chunk.title, "url": chunk.source_url})
                seen_sources.add(key)

        try:
            answer_text = await self.llm.chat_completion(
                system_prompt=system_prompt,
                user_prompt=f"Question: {question}\n\nKnowledge chunks:\n{context}",
                temperature=0.1
            )
            
            # --- JSON Leak Protection (Self-Correction) ---
            if answer_text.strip().startswith("{") and "tasks" in answer_text:
                logger.warning("Internal Planning Leak detected. Re-triggering generation with strict natural language enforcement.")
                answer_text = await self.llm.chat_completion(
                    system_prompt=system_prompt + "\n\nCRITICAL: You are talking to a HUMAN. DO NOT output JSON. Write a clear, conversational response in Markdown.",
                    user_prompt=f"Question: {question}\n\nKnowledge chunks:\n{context}",
                    temperature=0.3 # Increase temperature slightly to break the loop
                )

            if not answer_text:
                best = chunks[0].content.strip() if chunks else ""
                answer_text = best[:900] or "I couldn't find this in your company's knowledge base."

            return Answer(answer_text=answer_text, sources=sources)
        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            best = chunks[0].content.strip() if chunks else ""
            return Answer(answer_text=best[:900] or "I couldn't find this in your company's knowledge base.", sources=sources)
