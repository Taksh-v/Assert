from datetime import datetime
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

    async def check_cache(
        self, workspace_id: str, question: str, session: Optional[Any] = None, context_files: Optional[List[str]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Check if a similar question has been answered before.
        """
        try:
            await self._ensure_collection()
            
            query_vector = await self.embedder.aembed([question])
            results = await self.vector_store.async_search(
                workspace_id=workspace_id,
                query_vector=query_vector[0],
                top_k=1,
                vector_name="content"
            )
            
            if results and results[0]["score"] > 0.95:
                hit = results[0]
                metadata = hit["metadata"]
                
                # Check for database-backed freshness if session is provided
                if session:
                    from backend.models.connector import Connector
                    from sqlalchemy import select, func
                    
                    stmt = select(func.max(Connector.last_synced_at)).where(
                        Connector.workspace_id == workspace_id
                    )
                    res = await session.execute(stmt)
                    max_last_synced = res.scalar()
                    
                    created_at_str = metadata.get("created_at")
                    
                    if max_last_synced and isinstance(max_last_synced, datetime):
                        if not created_at_str:
                            logger.info("Semantic cache entry missing created_at timestamp. Invalidating legacy cache.")
                            return None
                        
                        try:
                            cache_created_at = datetime.fromisoformat(created_at_str)
                            # Align timezones for comparison (ensure both are naive UTC datetimes)
                            if max_last_synced.tzinfo is not None:
                                max_last_synced = max_last_synced.replace(tzinfo=None)
                            if cache_created_at.tzinfo is not None:
                                cache_created_at = cache_created_at.replace(tzinfo=None)
                            
                            if max_last_synced > cache_created_at:
                                logger.info(
                                    f"Semantic cache stale. Workspace synced at {max_last_synced}, "
                                    f"cache created at {cache_created_at}. Invalidating cache."
                                )
                                return None
                        except Exception as te:
                            logger.error(f"Error parsing semantic cache timestamps: {te}")
                
                # Check for context_files match
                cached_context_files_str = metadata.get("context_files", "[]")
                try:
                    cached_context_files = json.loads(cached_context_files_str)
                except Exception:
                    cached_context_files = []
                
                req_context_files = context_files or []
                if sorted(cached_context_files) != sorted(req_context_files):
                    logger.info(
                        f"Semantic cache context mismatch. Cached context files: {cached_context_files}, "
                        f"requested context files: {req_context_files}. Cache miss."
                    )
                    return None

                logger.info(f"Semantic cache hit! Similarity: {results[0]['score']}")
                return {
                    "answer": metadata.get("answer"),
                    "sources": json.loads(metadata.get("sources", "[]")),
                    "cached": True,
                    "similarity": hit["score"]
                }
        except Exception as e:
            logger.error(f"Error checking semantic cache: {e}")
        
        return None

    async def set_cache(self, workspace_id: str, question: str, result: Dict[str, Any], context_files: Optional[List[str]] = None):
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
                "created_at": datetime.utcnow().isoformat(),
                "context_files": json.dumps(context_files) if context_files else "[]",
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

    def purge_workspace_cache(self, workspace_id: str):
        """
        Delete all cache entries for a given workspace_id.
        """
        try:
            self.vector_store.delete_by_workspace(workspace_id)
            logger.info(f"Purged semantic cache for workspace: {workspace_id}")
        except Exception as e:
            logger.error(f"Error purging semantic cache: {e}")


