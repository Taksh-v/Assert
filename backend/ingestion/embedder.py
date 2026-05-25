import logging
from typing import List, Dict
import hashlib
import os
import numpy as np
from backend.core.config import get_settings
from backend.core.async_utils import run_blocking

settings = get_settings()
logger = logging.getLogger(__name__)
FALLBACK_MODEL = object()


class Embedder:
    """
    Generates embeddings for text chunks.
    Supports local (sentence-transformers) and OpenAI providers.
    """

    def __init__(self):
        self.provider = settings.embedding_provider
        self.model_name = settings.embedding_model
        self._model = None

    def _get_model(self):
        if self._model is None:
            if self.provider == "local":
                if settings.is_development and not os.environ.get("ASSEST_LOAD_LOCAL_MODELS"):
                    logger.info("Skipping local embedding model load in development; using hash embeddings")
                    self._model = FALLBACK_MODEL
                    return self._model

                from sentence_transformers import SentenceTransformer
                logger.info(f"Loading local embedding model: {self.model_name}")
                self._model = SentenceTransformer(self.model_name, local_files_only=True)
            elif self.provider == "openai":
                # OpenAI implementation would use the openai library
                logger.info("Using OpenAI embedding provider")
        return self._model

    def embed(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for a list of strings with batching.
        """
        if not texts:
            return []

        # Use batching for efficiency
        BATCH_SIZE = 100
        all_embeddings = []
        
        for i in range(0, len(texts), BATCH_SIZE):
            batch = [str(t) if t else "" for t in texts[i:i+BATCH_SIZE]]
            
            if self.provider == "local":
                try:
                    model = self._get_model()
                    if model is FALLBACK_MODEL:
                        all_embeddings.extend([self._hash_embedding(text) for text in batch])
                    else:
                        embeddings = model.encode(batch)
                        all_embeddings.extend(embeddings.tolist())
                except Exception as e:
                    logger.warning(f"Local embedding model unavailable, using hash embeddings: {e}")
                    all_embeddings.extend([self._hash_embedding(text) for text in batch])
            
            elif self.provider == "openai":
                if not settings.openai_api_key:
                    logger.error("OpenAI API key missing")
                    all_embeddings.extend([[0.0] * 1536 for _ in batch])
                    continue
                
                try:
                    from openai import OpenAI
                    client = OpenAI(api_key=settings.openai_api_key)
                    response = client.embeddings.create(
                        model=self.model_name or "text-embedding-3-small",
                        input=batch
                    )
                    all_embeddings.extend([data.embedding for data in response.data])
                except Exception as e:
                    logger.error(f"OpenAI embedding error: {e}")
                    all_embeddings.extend([[0.0] * 1536 for _ in batch])
        
        return all_embeddings

    def embed_multi(self, chunks: List[str], title: str, summary: str) -> List[Dict[str, List[float]]]:
        """
        Blueprint Layer 8: Multi-Vector Embeddings.
        Generates distinct vectors for content, title, and summary.
        """
        if not chunks:
            return []
            
        # 1. Embed all content chunks
        content_vectors = self.embed(chunks)
        
        # 2. Embed the title (repeated for every chunk context)
        title_vector = self.embed([title])[0]
        
        # 3. Embed the summary (repeated for every chunk context)
        summary_vector = self.embed([summary])[0] if summary else [0.0] * len(title_vector)
        
        multi_vectors = []
        for cv in content_vectors:
            multi_vectors.append({
                "content": cv,
                "title": title_vector,
                "summary": summary_vector
            })
            
        return multi_vectors

    async def aembed(self, texts: List[str]) -> List[List[float]]:
        """Async wrapper for `embed` to avoid blocking the event loop."""
        return await run_blocking(self.embed, texts)

    async def aembed_multi(self, chunks: List[str], title: str, summary: str) -> List[Dict[str, List[float]]]:
        """Async wrapper for `embed_multi`."""
        return await run_blocking(self.embed_multi, chunks, title, summary)

    def _hash_embedding(self, text: str, dimensions: int = 384) -> List[float]:
        """Deterministic fallback embedding for local/dev operation without model downloads."""
        vector = np.zeros(dimensions, dtype=np.float32)
        tokens = str(text).lower().split()
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            idx = int.from_bytes(digest[:4], "big") % dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[idx] += sign
        norm = np.linalg.norm(vector)
        if norm > 0:
            vector = vector / norm
        return vector.tolist()

