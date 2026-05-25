import logging
import json
from typing import Optional, Dict, Any, List
from backend.core.vector_store import VectorStore
from backend.ingestion.embedder import Embedder
from backend.core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

CACHE_COLLECTION_NAME = "semantic_cache"

class SemanticCache:
    """
    Semantic Cache for query results using Qdrant.
    """
    def __init__(self):
        self.vector_store = VectorStore(collection_name=CACHE_COLLECTION_NAME)
        self.embedder = Embedder()
        self._initialized = False

    async def _ensure_collection(self):
        if not self._initialized:
            # Typical embedding size for MiniLM-L6-v2 is 384
            # For OpenAI text-embedding-3-small it's 1536
            # We'll get a sample embedding to determine size if needed, 
            # but let's assume the embedder can tell us or we just use a default.
            sample_embedding = await self.embedder.aembed(["test"])
            vector_size = len(sample_embedding[0])
            self.vector_store.create_collection(vector_size=vector_size)
            self._initialized = True

    async def check_cache(self, workspace_id: str, question: str) -> Optional[Dict[str, Any]]:
        """
        Check if a similar question has been answered before.
        """
        try:
            await self._ensure_collection()
            
            query_vector = await self.embedder.aembed([question])
            results = self.vector_store.search(
                workspace_id=workspace_id,
                query_vector=query_vector[0],
                top_k=1,
                vector_name="content"
            )
            
            if results and results[0]["score"] > 0.95:
                logger.info(f"Semantic cache hit! Similarity: {results[0]['score']}")
                hit = results[0]
                metadata = hit["metadata"]
                
                return {
                    "answer": metadata.get("answer"),
                    "sources": json.loads(metadata.get("sources", "[]")),
                    "cached": True,
                    "similarity": hit["score"]
                }
        except Exception as e:
            logger.error(f"Error checking semantic cache: {e}")
        
        return None

    async def set_cache(self, workspace_id: str, question: str, result: Dict[str, Any]):
        """
        Store a query result in the semantic cache.
        """
        try:
            await self._ensure_collection()
            
            query_vector = await self.embedder.aembed([question])
            
            # Use multi-vector format as expected by VectorStore.upsert_batch
            vectors = [{
                "content": query_vector[0],
                "title": [0.0] * len(query_vector[0]),
                "summary": [0.0] * len(query_vector[0])
            }]
            
            payloads = [{
                "question": question,
                "answer": result.get("answer"),
                "sources": json.dumps(result.get("sources", [])),
                "is_active": True # VectorStore search filters for is_active: True
            }]
            
            self.vector_store.upsert_batch(
                workspace_id=workspace_id,
                vectors=vectors,
                payloads=payloads
            )
            logger.info(f"Stored result in semantic cache for: {question[:50]}...")
        except Exception as e:
            logger.error(f"Error setting semantic cache: {e}")
