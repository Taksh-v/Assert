from fastapi import APIRouter, Response
from backend.core.config import get_settings
from backend.core.database import async_session
from backend.core.vector_store import VectorStore
from backend.core.llm_client import LLMClient
from sqlalchemy import text
import asyncio
import logging

router = APIRouter(tags=["System"])
settings = get_settings()
logger = logging.getLogger(__name__)

# optional prometheus exposition
try:
    from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
    _PROM_AVAILABLE = True
except Exception:
    _PROM_AVAILABLE = False

@router.get("/health/live")
async def liveness_check():
    """Simple liveness check for startup synchronization."""
    return {"status": "alive", "timestamp": asyncio.get_event_loop().time()}

@router.get("/health")
async def health_check():
    """
    Comprehensive Brain Health Check.
    Verifies Sensory, Attention, and Executive layer connectivity.
    """
    health = {
        "status": "healthy",
        "version": settings.app_version,
        "layers": {
            "executive": {"status": "unknown", "engine": "LiteLLM/Ollama"},
            "attention": {"status": "unknown", "engine": "Qdrant"},
            "memory": {"status": "unknown", "engine": "PostgreSQL"},
            "cache": {"status": "unknown", "engine": "Qdrant Cache"}
        }
    }

    # 1. Check Executive Layer (LLM Proxy)
    try:
        # Just check if we can instantiate the client (it's fast)
        # We avoid a real ping here to keep it fast
        client = LLMClient()
        health["layers"]["executive"]["status"] = "connected"
    except Exception:
        health["layers"]["executive"]["status"] = "offline"

    # 2 & 4. Check Attention (Vector Store) and Cache (Semantic Cache) Layers
    try:
        from backend.core.vector_store import get_qdrant_client_ctx
        from backend.query.semantic_cache import CACHE_COLLECTION_NAME
        with get_qdrant_client_ctx() as client:
            if client:
                health["layers"]["attention"]["status"] = "connected"
                # Check cache layer within the same connection to avoid file lock contention
                try:
                    collections = client.get_collections().collections
                    exists = any(c.name == CACHE_COLLECTION_NAME for c in collections)
                    health["layers"]["cache"]["status"] = "connected" if exists else "offline"
                except Exception:
                    health["layers"]["cache"]["status"] = "offline"
            else:
                health["layers"]["attention"]["status"] = "offline"
                health["layers"]["cache"]["status"] = "offline"
    except Exception:
        health["layers"]["attention"]["status"] = "error"
        health["layers"]["cache"]["status"] = "offline"

    # 3. Check Memory Layer (Postgres)
    try:
        # Use a short timeout for the DB check
        async with async_session() as session:
            await asyncio.wait_for(session.execute(text("SELECT 1")), timeout=2.0)
            health["layers"]["memory"]["status"] = "connected"
            
            # Count users for provisioning verification
            user_count = (await session.execute(text("SELECT count(*) FROM users"))).scalar()
            ws_count = (await session.execute(text("SELECT count(*) FROM workspaces"))).scalar()
            health["layers"]["memory"]["provisioned"] = {
                "users": user_count,
                "workspaces": ws_count
            }
    except Exception as e:
        health["layers"]["memory"]["status"] = f"offline: {str(e)}"

    # Overall Status
    if any(l["status"] == "offline" for l in health["layers"].values()):
        health["status"] = "degraded"
        
    return health

@router.get("/health/db-stats")
async def get_db_stats():
    """Returns row counts for key tables and vector counts from Qdrant."""
    stats = {"postgres": {}, "qdrant": {}}
    
    # 1. Postgres Row Counts
    try:
        async with async_session() as session:
            for table in ["users", "memories", "conversations"]:
                res = await session.execute(text(f"SELECT count(*) FROM {table}"))
                stats["postgres"][table] = res.scalar()
    except Exception as e:
        stats["postgres"] = {"error": str(e)}

    # 2. Qdrant Vector Counts
    try:
        from backend.core.vector_store import get_qdrant_client_ctx
        with get_qdrant_client_ctx() as client:
            collections = client.get_collections().collections
            for col in collections:
                info = client.get_collection(col.name)
                stats["qdrant"][col.name] = info.points_count
    except Exception as e:
        stats["qdrant"] = {"error": str(e)}
        
    return stats

@router.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint; returns 501 if prometheus_client unavailable."""
    if not _PROM_AVAILABLE:
        return Response(status_code=501, content="Prometheus client not installed")
    data = generate_latest()
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)
