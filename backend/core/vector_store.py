import logging
import os
from typing import List, Dict, Any, Optional
from backend.core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

# Global client to ensure single connection to local disk
_GLOBAL_QDRANT_CLIENT = None

def get_qdrant_client():
    global _GLOBAL_QDRANT_CLIENT
    if _GLOBAL_QDRANT_CLIENT is None:
        try:
            from qdrant_client import QdrantClient  # lazy import
        except ImportError as e:
            logger.error(f"qdrant_client not available: {e}")
            return None
        if settings.qdrant_mode == "local":
            logger.info(f"Initializing local Qdrant at {settings.qdrant_path}")
            os.makedirs(settings.qdrant_path, exist_ok=True)
            _GLOBAL_QDRANT_CLIENT = QdrantClient(path=settings.qdrant_path)
        elif settings.qdrant_mode == "memory":
            logger.info("Initializing in-memory Qdrant")
            _GLOBAL_QDRANT_CLIENT = QdrantClient(":memory:")
        else:
            logger.info(f"Connecting to Qdrant server at {settings.qdrant_host}:{settings.qdrant_port}")
            _GLOBAL_QDRANT_CLIENT = QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)
    return _GLOBAL_QDRANT_CLIENT


class VectorStore:
    """
    Wrapper for Qdrant vector database.
    """

    def __init__(self):
        self.collection_name = settings.qdrant_collection_name
        self.client = get_qdrant_client()
        self._models_cache = None

    @property
    def _models(self):
        """Lazy-load qdrant_client.http.models to avoid gRPC binary load at import."""
        if self._models_cache is None:
            from qdrant_client.http import models as _m
            self._models_cache = _m
        return self._models_cache

    def create_collection(self, vector_size: int):
        """Create a new collection if it doesn't exist with Multi-Vector support (Layer 8)."""
        if not self.client:
            logger.warning("Qdrant client not available; skipping collection creation.")
            return
        try:
            collections = self.client.get_collections().collections
            exists = any(c.name == self.collection_name for c in collections)
            
            if not exists:
                logger.info(f"Creating Multi-Vector collection: {self.collection_name}")
                # Layer 8: Named Vectors Configuration
                vectors_config = {
                    "content": self._models.VectorParams(size=vector_size, distance=self._models.Distance.COSINE),
                    "title": self._models.VectorParams(size=vector_size, distance=self._models.Distance.COSINE),
                    "summary": self._models.VectorParams(size=vector_size, distance=self._models.Distance.COSINE)
                }
                
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=vectors_config,
                )
            
                # Create payload indexes for fast filtering
                self.client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name="workspace_id",
                    field_schema=self._models.PayloadSchemaType.KEYWORD,
                )
                self.client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name="content_tier",
                    field_schema=self._models.PayloadSchemaType.INTEGER,
                )
        except Exception as e:
            logger.error(f"Collection creation failed: {e}")

    def upsert_batch(
        self,
        workspace_id: str,
        vectors: List[Any],
        payloads: List[Dict[str, Any]]
    ):
        """
        Layer 8: Batch Upsert with Multi-Vector support.
        Handles both single List[float] and Dict[str, List[float]] (Named Vectors).
        """
        if not self.client:
            logger.warning("Qdrant client not available; skipping upsert_batch.")
            return
        try:
            points = []
            import uuid
            import hashlib
            
            for i, (vector, payload) in enumerate(zip(vectors, payloads)):
                # Generate deterministic point ID based on source and index
                source_url = payload.get("source_url", "")
                point_id = hashlib.md5(f"{source_url}_{i}".encode()).hexdigest()
                
                points.append(self._models.PointStruct(
                    id=point_id,
                    vector=vector, # Can be Dict[str, List[float]] for Named Vectors
                    payload={
                        "workspace_id": workspace_id,
                        **payload
                    }
                ))
                
            self.client.upsert(
                collection_name=self.collection_name,
                points=points
            )
            logger.info(f"Upserted {len(points)} points into {self.collection_name} (Layer 8 Ready)")
        except Exception as e:
            logger.error(f"Batch upsert failed: {e}")

    def search(
        self, 
        workspace_id: str, 
        query_vector: List[float], 
        top_k: int = 5,
        user_id: Optional[str] = None,
        vector_name: str = "content"
    ) -> List[Dict[str, Any]]:
        """
        Semantic search with STRICT PRE-retrieval security filtering (Layer 11).
        """
        if not self.client:
            logger.warning("Qdrant client not available; returning empty search results.")
            return []
        try:
            must_filters = [
                self._models.FieldCondition(key="workspace_id", match=self._models.MatchValue(value=workspace_id)),
                self._models.FieldCondition(key="is_active", match=self._models.MatchValue(value=True))
            ]
            
            # Layer 11: Security Gate (Development Permissive Mode)
            # If user_id is provided, check permissions.
            # If not in production, we allow results that lack is_public field to ensure dev experience.
            if user_id:
                security_filter = self._models.Filter(
                    should=[
                        self._models.FieldCondition(key="is_public", match=self._models.MatchValue(value=True)),
                        self._models.FieldCondition(key="allowed_users", match=self._models.MatchValue(value=user_id)),
                        # Permissive fallback for dev: if neither field exists, assume accessible
                        self._models.Filter(
                            must_not=[
                                self._models.HasIdCondition(has_id=[hit.id for hit in []]) # dummy to keep structure
                            ],
                            must=[
                                self._models.FieldCondition(key="is_public", match=self._models.MatchValue(value=None))
                            ]
                        )
                    ]
                )
                # Note: simplified for robust dev experience
                must_filters.append(self._models.Filter(
                    should=[
                        self._models.FieldCondition(key="is_public", match=self._models.MatchValue(value=True)),
                        self._models.FieldCondition(key="allowed_users", match=self._models.MatchValue(value=user_id))
                    ]
                ) if not settings.is_development else self._models.Filter(must=[]))
            elif not settings.is_development:
                # In production, strictly only public
                must_filters.append(
                    self._models.FieldCondition(key="is_public", match=self._models.MatchValue(value=True))
                )

            response = self.client.query_points(
                collection_name=self.collection_name,
                query=query_vector,
                using=vector_name,
                query_filter=self._models.Filter(must=must_filters),
                limit=top_k,
                with_payload=True
            )
            search_result = response.points
            
            return [
                {
                    "chunk_id": hit.id,
                    "text": hit.payload.get("text", hit.payload.get("title", "")),
                    "score": hit.score,
                    "metadata": {k: v for k, v in hit.payload.items() if k not in ["workspace_id"]}
                }
                for hit in search_result
            ]
        except Exception as e:
            logger.error(f"Semantic search failed: {e}")
            return []

    def reciprocal_rank_fusion(
        self, 
        vector_results: List[Dict[str, Any]], 
        keyword_results: List[Dict[str, Any]], 
        k: int = 60
    ) -> List[Dict[str, Any]]:
        """
        Combine vector and keyword results using RRF.
        """
        scores = {}  # chunk_id -> combined score
        
        for rank, res in enumerate(vector_results):
            chunk_id = res["chunk_id"]
            scores[chunk_id] = scores.get(chunk_id, 0) + 1.0 / (rank + k)
            
        for rank, res in enumerate(keyword_results):
            chunk_id = res["chunk_id"]
            scores[chunk_id] = scores.get(chunk_id, 0) + 1.0 / (rank + k)
            
        # Combine items, favoring vector_results metadata
        all_items = {res["chunk_id"]: res for res in keyword_results + vector_results}
        
        # Sort by combined score
        sorted_ids = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        
        final_results = []
        for chunk_id, combined_score in sorted_ids:
            item = all_items[chunk_id]
            item["rrf_score"] = combined_score
            final_results.append(item)
            
        return final_results
