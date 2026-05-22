"""
Quick Retriever Agent — For QUICK_LOOKUP queries.

Handles simple factual lookups. Bypasses the full Planner/Analyst/Synthesizer
swarm and instead performs a single fast retrieval + synthesis pass.
Significantly reduces latency (from ~20s down to ~2s) and token usage.
"""
import logging
from typing import Dict, Any, Optional

from backend.core.config import get_settings
from backend.retrieval.orchestrator import RetrievalOrchestrator

settings = get_settings()
logger = logging.getLogger(__name__)


class QuickRetrieverAgent:
    """Specialist for fast, single-pass factual lookups."""

    def __init__(self):
        self.retrieval_orchestrator = RetrievalOrchestrator()
        self._client = None
        self._client_init_failed = False

    @property
    def client(self):
        if self._client is not None:
            return self._client
        if self._client_init_failed or not settings.groq_api_key:
            return None
        try:
            from groq import Groq
            self._client = Groq(api_key=settings.groq_api_key)
            return self._client
        except Exception as e:
            self._client_init_failed = True
            return None

    async def execute(self, query: str, workspace_id: str, user_id: Optional[str] = None) -> Dict[str, Any]:
        """Perform a single fast retrieval and synthesis."""
        logger.info(f"QuickRetriever executing for query: '{query}'")

        # 1. Retrieve context
        context = await self.retrieval_orchestrator.retrieve_reasoning_context(
            query=query,
            workspace_id=workspace_id,
            user_id=user_id
        )

        # 2. Synthesize answer
        if not self.client:
            return {
                "answer": "Error: LLM client unavailable for quick synthesis.",
                "confidence": 0.0,
                "sources": []
            }

        prompt = f"""You are a helpful assistant providing a quick, direct answer to a user's question.
Use ONLY the provided context. If the answer is not in the context, say "I don't have enough information to answer that."
Be concise. Do not write a long essay.

Context:
{context}

Question: {query}

Answer:"""

        try:
            response = self.client.chat.completions.create(
                messages=[
                    {"role": "system", "content": "You are a concise, factual assistant."},
                    {"role": "user", "content": prompt}
                ],
                model=settings.groq_model,
                temperature=0.3,
            )

            answer = response.choices[0].message.content

            # Calculate a basic confidence score based on length of context
            confidence = 0.9 if context and len(context) > 100 else 0.4
            if "I don't have enough information" in answer:
                confidence = 0.1

            return {
                "answer": answer,
                "confidence": confidence,
                "sources": ["quick_retrieval"]
            }

        except Exception as e:
            logger.error(f"QuickRetriever synthesis failed: {e}")
            return {
                "answer": f"I encountered an error trying to answer your question: {e}",
                "confidence": 0.0,
                "sources": []
            }
