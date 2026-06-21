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
    All checks run in parallel for minimum latency.
    """
    health = {
        "status": "healthy",
        "version": settings.app_version,
        "layers": {
            "executive": {"status": "unknown", "engine": "LiteLLM/Ollama"},
            "attention": {"status": "unknown", "engine": "Qdrant"},
            "memory": {"status": "unknown", "engine": "PostgreSQL"},
            "cache_l1": {"status": "unknown", "engine": "Redis"},
            "cache_l2": {"status": "unknown", "engine": "Qdrant Semantic Cache"},
        }
    }

    async def check_executive():
        """Check Executive Layer (LLM Proxy) — fast instantiation check."""
        try:
            LLMClient()
            health["layers"]["executive"]["status"] = "connected"
        except Exception:
            health["layers"]["executive"]["status"] = "offline"

    async def check_attention_and_cache_l2():
        """Check Attention (Vector Store) and L2 Semantic Cache layers."""
        try:
            from backend.core.vector_store import get_qdrant_client_ctx
            from backend.query.semantic_cache import CACHE_COLLECTION_NAME
            with get_qdrant_client_ctx() as client:
                if client:
                    health["layers"]["attention"]["status"] = "connected"
                    try:
                        collections = client.get_collections().collections
                        exists = any(c.name == CACHE_COLLECTION_NAME for c in collections)
                        health["layers"]["cache_l2"]["status"] = "connected" if exists else "offline"
                    except Exception:
                        health["layers"]["cache_l2"]["status"] = "offline"
                else:
                    health["layers"]["attention"]["status"] = "offline"
                    health["layers"]["cache_l2"]["status"] = "offline"
        except Exception:
            health["layers"]["attention"]["status"] = "error"
            health["layers"]["cache_l2"]["status"] = "offline"

    async def check_cache_l1():
        """Check L1 Redis hot cache layer."""
        from backend.core.redis_client import redis_health_check
        health["layers"]["cache_l1"] = await redis_health_check()

    async def check_memory():
        """Check Memory Layer (Postgres) — reduced 3s timeout, no COUNT(*)."""
        try:
            async with async_session() as session:
                await asyncio.wait_for(session.execute(text("SELECT 1")), timeout=3.0)
                health["layers"]["memory"]["status"] = "connected"
        except Exception as e:
            health["layers"]["memory"]["status"] = f"offline: {str(e)}"

    await asyncio.gather(
        check_executive(),
        check_attention_and_cache_l2(),
        check_cache_l1(),
        check_memory(),
        return_exceptions=True,
    )

    # Overall Status
    if any(l["status"] == "offline" or l["status"].startswith("offline:") 
           for l in health["layers"].values() 
           if isinstance(l["status"], str)):
        health["status"] = "degraded"
        
    return health


@router.get("/health/ready")
async def readiness_check():
    """
    Strict readiness probe — returns 503 if any critical dependency is offline.
    Use for Kubernetes readiness; liveness should use /health/live.
    """
    from fastapi.responses import JSONResponse

    health = await health_check()
    critical = ("memory", "attention")
    degraded = any(
        health["layers"][layer]["status"] in ("offline", "error")
        or str(health["layers"][layer]["status"]).startswith("offline:")
        for layer in critical
    )
    if degraded:
        return JSONResponse(status_code=503, content=health)
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
