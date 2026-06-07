import logging
from typing import List, Dict, Any
from backend.core.llm_impl import SharedLLMClient
from backend.ingestion.embedder import Embedder

logger = logging.getLogger(__name__)

class HyDEGenerator:
    """
    Hypothetical Document Embeddings (HyDE) query generator.
    Translates a sparse or colloquial user question into a hypothetical ideal answer structure
    before generating search embeddings. This resolves syntax/vocabulary mismatches during RAG searches.
    """

    def __init__(self):
        self.llm_client = SharedLLMClient(model_type="fast")
        self.embedder = Embedder()

    async def generate_hypothetical_document(self, question: str) -> str:
        """
        Generates a hypothetical answers/documents matching the question scope.
        """
        system_prompt = (
            "You are an expert technical document generator. "
            "Write a short paragraph answering the user's question. "
            "Do not state whether you know the answer; simply write a hypothetical document or section "
            "that would perfectly answer the query. Use professional, clean documentation tone."
        )
        
        user_prompt = f"Question: {question}\n\nHypothetical Document Draft:"
        
        try:
            hypothetical_doc = await self.llm_client.chat_completion(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.4,
                max_tokens=200
            )
            logger.info("Successfully generated hypothetical document for query: %s", question[:50])
            return hypothetical_doc.strip()
        except Exception as e:
            logger.error("Failed to generate HyDE document, falling back to original query text: %s", e)
            return question

    async def get_hyde_embedding(self, question: str) -> List[float]:
        """
        Generates the vector embedding for the hypothetical document corresponding to the query.
        """
        hypothetical_doc = await self.generate_hypothetical_document(question)
        # We run the synchronous embedding function using run_blocking or directly
        embeddings = self.embedder.embed([hypothetical_doc])
        if embeddings and len(embeddings) > 0:
            return embeddings[0]
        # Return a zero vector fallback if embedding fails
        return [0.0] * 384
