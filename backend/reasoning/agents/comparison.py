"""
Comparison Agent — For COMPARISON queries.

Specializes in cross-referencing multiple documents/entities and generating
structured comparison tables. Bypasses the standard sequential planner.
"""
import logging
from typing import Dict, Any, Optional

from backend.core.config import get_settings
from backend.retrieval.orchestrator import RetrievalOrchestrator

settings = get_settings()
logger = logging.getLogger(__name__)


class ComparisonAgent:
    """Specialist for cross-document comparisons."""

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
        """Perform targeted retrieval and generate a comparison table."""
        logger.info(f"ComparisonAgent executing for query: '{query}'")

        # 1. Retrieve deep context
        context = await self.retrieval_orchestrator.retrieve_reasoning_context(
            query=query,
            workspace_id=workspace_id,
            user_id=user_id
        )

        # 2. Synthesize comparison
        if not self.client:
            return {
                "answer": "Error: LLM client unavailable for comparison.",
                "confidence": 0.0,
                "sources": []
            }

        prompt = f"""You are a senior analyst tasked with comparing multiple entities or concepts.

Your task:
1. Identify the entities being compared based on the user's query.
2. Analyze the provided context for information about each entity.
3. Generate a structured Markdown table comparing them across relevant dimensions.
4. Provide a brief summary paragraph concluding the comparison.

If the context does not contain enough information to compare them, state that clearly.

Context:
{context}

Question: {query}

Comparison Analysis:"""

        try:
            response = self.client.chat.completions.create(
                messages=[
                    {"role": "system", "content": "You are a senior analyst who produces clear, structured Markdown tables."},
                    {"role": "user", "content": prompt}
                ],
                model=settings.groq_model,
                temperature=0.4,
            )

            answer = response.choices[0].message.content

            # Check if it successfully built a table
            confidence = 0.85 if "|" in answer and "-" in answer else 0.5
            if "I don't have enough information" in answer:
                confidence = 0.1

            return {
                "answer": answer,
                "confidence": confidence,
                "sources": ["comparison_retrieval"]
            }

        except Exception as e:
            logger.error(f"ComparisonAgent synthesis failed: {e}")
            return {
                "answer": f"I encountered an error trying to build the comparison: {e}",
                "confidence": 0.0,
                "sources": []
            }
