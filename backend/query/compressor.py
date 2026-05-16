import logging
from typing import List, Dict, Any
from backend.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class ContextCompressor:
    """
    Blueprint Layer 12: Context Compression.
    Summarizes and filters chunks to maximize information density for the LLM prompt.
    """

    def __init__(self):
        self._client = None
        self._client_init_failed = False
        self.model = "llama3-70b-8192"

    @property
    def client(self):
        if self._client is not None:
            return self._client
        if self._client_init_failed or not getattr(settings, 'groq_api_key', None):
            return None
        try:
            from groq import Groq
            self._client = Groq(api_key=settings.groq_api_key)
            return self._client
        except Exception as e:
            logger.warning(f"Groq init failed for ContextCompressor: {e}")
            self._client_init_failed = True
            return None

    async def compress(self, question: str, chunks: List[str]) -> str:
        """
        Compress multiple chunks into a single relevant context block.
        """
        if not chunks:
            return ""

        combined_text = "\n\n---\n\n".join(chunks)
        
        prompt = f"""
        You are a Context Compression Engine.
        Goal: Extract ONLY the information from the provided chunks that is relevant to the question.
        Constraint: Maintain factual accuracy and specific details (names, dates, numbers).
        Format: Return a dense, cohesive summary.

        Question: "{question}"
        
        Chunks:
        {combined_text[:6000]}
        
        Dense Relevant Context:
        """
        
        try:
            if not self.client:
                return combined_text[:4000]
            response = self.client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=self.model,
                temperature=0,
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Compression failed: {e}")
            # Fallback to simple concatenation
            return combined_text[:4000]
