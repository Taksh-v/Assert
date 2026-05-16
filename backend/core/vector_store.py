import logging
import os
from typing import List, Dict, Any, Optional
from qdrant_client import QdrantClient
from qdrant_client.http import models
from backend.core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

# Global client to ensure single connection to local disk
_GLOBAL_QDRANT_CLIENT = None

def get_qdrant_client():
    global _GLOBAL_QDRANT_CLIENT
    if _GLOBAL_QDRANT_CLIENT is None:
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

    def create_collection(self, vector_size: int):
        """Create a new collection if it doesn't exist with Multi-Vector support (Layer 8)."""
        collections = self.client.get_collections().collections
        exists = any(c.name == self.collection_name for c in collections)
        
        if not exists:
            logger.info(f"Creating Multi-Vector collection: {self.collection_name}")
            # Layer 8: Named Vectors Configuration
            vectors_config = {
                "content": models.VectorParams(size=vector_size, distance=models.Distance.COSINE),
                "title": models.VectorParams(size=vector_size, distance=models.Distance.COSINE),
                "summary": models.VectorParams(size=vector_size, distance=models.Distance.COSINE)
            }
            
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=vectors_config,
            )
            
            # Create payload indexes for fast filtering
            self.client.create_payload_index(
                collection_name=self.collection_name,
                field_name="workspace_id",
                field_schema=models.PayloadSchemaType.KEYWORD,
            )
            self.client.create_payload_index(
                collection_name=self.collection_name,
                field_name="content_tier",
                field_schema=models.PayloadSchemaType.INTEGER,
            )

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
        points = []
        import uuid
        import hashlib
        
        for i, (vector, payload) in enumerate(zip(vectors, payloads)):
            # Generate deterministic point ID based on source and index
            source_url = payload.get("source_url", "")
            point_id = hashlib.md5(f"{source_url}_{i}".encode()).hexdigest()
            
            points.append(models.PointStruct(
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
        must_filters = [
            models.FieldCondition(key="workspace_id", match=models.MatchValue(value=workspace_id)),
            models.FieldCondition(key="is_active", match=models.MatchValue(value=True))
        ]
        
        # Layer 11: Security Gate
        # Only show results if:
        # 1. The document is public (is_public=True)
        # 2. OR the user is specifically allowed (user_id in allowed_users)
        if user_id:
            must_filters.append(
                models.Filter(
                    should=[
                        models.FieldCondition(key="is_public", match=models.MatchValue(value=True)),
                        models.FieldCondition(key="allowed_users", match=models.MatchValue(value=user_id))
                    ]
                )
            )
        else:
            # If no user_id, ONLY show public content
            must_filters.append(
                models.FieldCondition(key="is_public", match=models.MatchValue(value=True))
            )

        search_result = self.client.search(
            collection_name=self.collection_name,
            query_vector=models.NamedVector(
                name=vector_name,
                vector=query_vector
            ),
            query_filter=models.Filter(must=must_filters),
            limit=top_k,
            with_payload=True
        )
        
        return [
            {
                "chunk_id": hit.id,
                "text": hit.payload.get("text", hit.payload.get("title", "")),
                "score": hit.score,
                "metadata": {k: v for k, v in hit.payload.items() if k not in ["workspace_id"]}
            }
            for hit in search_result
        ]

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
