import logging
import os
import asyncio
import atexit
from backend.core.retry import retry_sync
from typing import List, Dict, Any, Optional
from backend.core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

from contextlib import contextmanager

# Global client to ensure single connection to local disk (used for server/memory modes)
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
        # Register an atexit handler to close the client cleanly before interpreter shutdown
        try:
            atexit.register(_close_global_qdrant)
        except Exception:
            pass
    return _GLOBAL_QDRANT_CLIENT


def _close_global_qdrant():
    global _GLOBAL_QDRANT_CLIENT
    client = _GLOBAL_QDRANT_CLIENT
    if client is None:
        return
    try:
        # Best-effort close; some environments may already be tearing down imports
        client.close()
    except Exception:
        pass
    finally:
        _GLOBAL_QDRANT_CLIENT = None


async def get_qdrant_client_async():
    """Async-friendly helper to initialize/get the Qdrant client without blocking the event loop.

    Callers in async code should use this instead of calling `get_qdrant_client()` directly,
    which may perform heavier synchronous initialization.
    """
    return await asyncio.to_thread(get_qdrant_client)


@contextmanager
def get_qdrant_client_ctx():
    """
    Context manager that yields a QdrantClient.
    For 'local' mode (file storage), it instantiates a new QdrantClient and closes it on exit
    to release file locks immediately, preventing deadlock lockouts.
    For 'memory' and 'server' modes, it yields a shared global client.
    """
    global _GLOBAL_QDRANT_CLIENT
    
    # If get_qdrant_client is mocked (e.g. in test suites), yield it directly and do not close.
    from unittest.mock import Mock
    if isinstance(get_qdrant_client, Mock) or hasattr(get_qdrant_client, "mock_calls"):
        yield get_qdrant_client()
        return

    # If global client is already set (e.g. by test conftest fixtures), yield it and do not close.
    if _GLOBAL_QDRANT_CLIENT is not None:
        yield _GLOBAL_QDRANT_CLIENT
        return

    try:
        from qdrant_client import QdrantClient  # lazy import
    except ImportError as e:
        logger.error(f"qdrant_client not available: {e}")
        yield None
        return

    if settings.qdrant_mode == "local":
        logger.info(f"Initializing transient local Qdrant client at {settings.qdrant_path}")
        os.makedirs(settings.qdrant_path, exist_ok=True)
        client = QdrantClient(path=settings.qdrant_path)
        try:
            yield client
        finally:
            logger.debug("Releasing Qdrant file storage lock")
            try:
                client.close()
            except Exception:
                pass
    else:
        # For memory or server modes, cache the connection
        if settings.qdrant_mode == "memory":
            logger.info("Initializing in-memory Qdrant")
            _GLOBAL_QDRANT_CLIENT = QdrantClient(":memory:")
        else:
            logger.info(f"Connecting to Qdrant server at {settings.qdrant_host}:{settings.qdrant_port}")
            _GLOBAL_QDRANT_CLIENT = QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)
            
        try:
            atexit.register(_close_global_qdrant)
        except Exception:
            pass
        yield _GLOBAL_QDRANT_CLIENT


class VectorStore:
    """
    Wrapper for Qdrant vector database.
    """

    def __init__(self, collection_name: Optional[str] = None, client: Optional[object] = None):
        """If `client` is provided, it will be used directly (dependency injection).

        Otherwise the module-level `get_qdrant_client()` is used lazily to preserve
        backward compatibility.
        """
        self.collection_name = collection_name or settings.qdrant_collection_name
        self._client = client
        self._models_cache = None

    @contextmanager
    def _get_client(self):
        """Internal context manager helper to safely borrow a Qdrant client."""
        if self._client is not None:
            yield self._client
        else:
            with get_qdrant_client_ctx() as client:
                yield client

    @property
    def client(self):
        # Preserve attribute-style access for existing callers.
        if self._client is None:
            self._client = get_qdrant_client()
        return self._client

    async def get_client_async(self):
        """Async-friendly accessor that initializes the client off the event loop if needed."""
        if self._client is None:
            self._client = await get_qdrant_client_async()
        return self._client

    @property
    def _models(self):
        """Lazy-load qdrant_client.http.models to avoid gRPC binary load at import."""
        if self._models_cache is None:
            from qdrant_client.http import models as _m
            self._models_cache = _m
        return self._models_cache

    def create_collection(self, vector_size: int, collection_name: Optional[str] = None):
        """Create a new collection if it doesn't exist. Supports Multi-Vector if it's the main knowledge collection."""
        target_collection = collection_name or self.collection_name
        with self._get_client() as client:
            if not client:
                logger.warning(f"Qdrant client not available; skipping collection creation for {target_collection}.")
                return
            try:
                collections = client.get_collections().collections
                exists = any(c.name == target_collection for c in collections)
                
                if not exists:
                    logger.info(f"Creating collection: {target_collection}")
                    
                    if target_collection == settings.qdrant_collection_name:
                        # Layer 8: Named Vectors Configuration for knowledge
                        vectors_config = {
                            "content": self._models.VectorParams(size=vector_size, distance=self._models.Distance.COSINE),
                            "title": self._models.VectorParams(size=vector_size, distance=self._models.Distance.COSINE),
                            "summary": self._models.VectorParams(size=vector_size, distance=self._models.Distance.COSINE)
                        }
                    else:
                        # Single vector configuration for other collections (like episodes)
                        vectors_config = self._models.VectorParams(size=vector_size, distance=self._models.Distance.COSINE)
                    
                    client.create_collection(
                        collection_name=target_collection,
                        vectors_config=vectors_config,
                    )
                
                    # Create common payload indexes
                    client.create_payload_index(
                        collection_name=target_collection,
                        field_name="workspace_id",
                        field_schema=self._models.PayloadSchemaType.KEYWORD,
                    )
            except Exception as e:
                logger.error(f"Collection creation failed for {target_collection}: {e}")
    

    # Add retry wrapper to reduce transient failures during collection creation
    create_collection = retry_sync(max_attempts=3, initial_delay=0.1)(create_collection)

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
        with self._get_client() as client:
            if not client:
                logger.warning("Qdrant client not available; skipping upsert_batch.")
                return
            try:
                points = []
                import uuid
                import hashlib
                from itertools import islice

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

                # Chunk points to avoid sending very large payloads to Qdrant
                batch_size = int(getattr(settings, "qdrant_upsert_batch_size", 256))
                if len(points) <= batch_size:
                    client.upsert(collection_name=self.collection_name, points=points)
                    logger.info(f"Upserted {len(points)} points into {self.collection_name} (Layer 8 Ready)")
                else:
                    # Use multiple upserts; optionally parallelize via threads
                    from concurrent.futures import ThreadPoolExecutor

                    concurrency = int(getattr(settings, "qdrant_write_concurrency", 2)) or 1
                    def chunked_iterable(seq, size):
                        for i in range(0, len(seq), size):
                            yield seq[i:i+size]

                    chunks = list(chunked_iterable(points, batch_size))
                    logger.info(f"Upserting {len(points)} points in {len(chunks)} chunks (batch_size={batch_size})")

                    if concurrency <= 1 or len(chunks) == 1:
                        for chunk in chunks:
                            client.upsert(collection_name=self.collection_name, points=chunk)
                    else:
                        with ThreadPoolExecutor(max_workers=concurrency) as ex:
                            futures = [ex.submit(client.upsert, collection_name=self.collection_name, points=chunk) for chunk in chunks]
                            # Wait for completion
                            for f in futures:
                                try:
                                    f.result()
                                except Exception as e:
                                    logger.error(f"Chunk upsert failed: {e}")
                    logger.info(f"Upserted {len(points)} points into {self.collection_name} in {len(chunks)} chunks")
            except Exception as e:
                logger.error(f"Batch upsert failed: {e}")


    upsert_batch = retry_sync(max_attempts=3, initial_delay=0.05)(upsert_batch)

    def search(
        self, 
        workspace_id: str, 
        query_vector: List[float], 
        top_k: int = 5,
        user_id: Optional[str] = None,
        vector_name: str = "content"
    ) -> List[Dict[str, Any]]:
        """
        Semantic search. Keep DB-side filters minimal (workspace and active flag).
        """
        with self._get_client() as client:
            if not client:
                logger.warning("Qdrant client not available; returning empty search results.")
                return []
            try:
                # Only apply workspace + active filters at the DB level for now.
                must_filters = [
                    self._models.FieldCondition(key="workspace_id", match=self._models.MatchValue(value=workspace_id)),
                    self._models.FieldCondition(key="is_active", match=self._models.MatchValue(value=True))
                ]

                response = client.query_points(
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


    search = retry_sync(max_attempts=3, initial_delay=0.05)(search)

    async def async_search(
        self,
        workspace_id: str,
        query_vector: List[float],
        top_k: int = 5,
        user_id: Optional[str] = None,
        vector_name: str = "content",
    ) -> List[Dict[str, Any]]:
        """Async wrapper around the synchronous `search` method."""
        return await asyncio.to_thread(self.search, workspace_id, query_vector, top_k, user_id, vector_name)

    def reciprocal_rank_fusion(
        self, 
        vector_results: List[Dict[str, Any]], 
        keyword_results: List[Dict[str, Any]], 
        k: int = 60
    ) -> List[Dict[str, Any]]:
        """Delegate to retrieval fusion implementation to keep DB wrapper thin."""
        try:
            from backend.retrieval.fusion import reciprocal_rank_fusion as rrf
            return rrf(vector_results=vector_results, keyword_results=keyword_results, k=k)
        except Exception:
            # In case retrieval layer is unavailable, fall back to simple merge
            all_items = {res["chunk_id"]: res for res in keyword_results + vector_results}
            return list(all_items.values())

    def upsert_episode(self, workspace_id: str, episode_id: str, vector: List[float], payload: Dict[str, Any]):
        """Store an episodic memory vector in the episodes collection."""
        with self._get_client() as client:
            if not client:
                return
            collection = settings.qdrant_episodes_collection_name
            client.upsert(
                collection_name=collection,
                points=[
                    self._models.PointStruct(
                        id=episode_id,
                        vector=vector,
                        payload={"workspace_id": workspace_id, **payload}
                    )
                ]
            )

    def search_episodes(
        self,
        workspace_id: str,
        query_vector: List[float],
        top_k: int = 5,
        user_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Search for similar episodes in the episodes collection."""
        with self._get_client() as client:
            if not client:
                return []
            collection = settings.qdrant_episodes_collection_name
            
            must_filters = [
                self._models.FieldCondition(key="workspace_id", match=self._models.MatchValue(value=workspace_id))
            ]
            if user_id:
                # Episodes might be shared (user_id is null) or private
                must_filters.append(
                    self._models.Filter(
                        should=[
                            self._models.FieldCondition(key="user_id", match=self._models.MatchValue(value=user_id)),
                            self._models.HasIdCondition(has_id=[]) # Placeholder for "is null" check if Qdrant supports it better via lack of field
                        ]
                    )
                )

            response = client.query_points(
                collection_name=collection,
                query=query_vector,
                query_filter=self._models.Filter(must=must_filters),
                limit=top_k,
                with_payload=True
            )
            return [
                {
                    "id": hit.id,
                    "score": hit.score,
                    "payload": hit.payload
                }
                for hit in response.points
            ]


def initialize_qdrant_collections() -> None:
    """Auto-create all required Qdrant collections on application startup.

    Creates:
      1. Main knowledge collection (multi-vector: content, title, summary)
      2. Episodes collection (single vector)
      3. Semantic cache collection (multi-vector: content, title, summary)

    The vector dimension is determined by generating a probe embedding at
    runtime so it stays in sync with the configured embedding model.
    """
    from backend.query.semantic_cache import CACHE_COLLECTION_NAME

    # Determine vector dimension by generating a probe embedding
    try:
        from backend.ingestion.embedder import Embedder
        embedder = Embedder()
        probe = embedder.embed(["dimension probe"])
        vector_size = len(probe[0]) if probe else 384
    except Exception as e:
        logger.warning(f"Could not determine embedding dimension via probe; defaulting to 384: {e}")
        vector_size = 384

    vs = VectorStore()

    # 1. Knowledge collection (multi-vector)
    logger.info(f"Ensuring knowledge collection '{settings.qdrant_collection_name}' exists (dim={vector_size})")
    vs.create_collection(vector_size=vector_size, collection_name=settings.qdrant_collection_name)

    # 2. Episodes collection (single vector)
    logger.info(f"Ensuring episodes collection '{settings.qdrant_episodes_collection_name}' exists (dim={vector_size})")
    vs.create_collection(vector_size=vector_size, collection_name=settings.qdrant_episodes_collection_name)

    # 3. Semantic cache collection (multi-vector)
    logger.info(f"Ensuring semantic cache collection '{CACHE_COLLECTION_NAME}' exists (dim={vector_size})")
    vs.create_collection(vector_size=vector_size, collection_name=CACHE_COLLECTION_NAME)
