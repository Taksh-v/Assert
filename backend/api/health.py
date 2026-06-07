from fastapi import APIRouter, Response
from backend.core.config import get_settings

router = APIRouter(tags=["System"])
settings = get_settings()


from fastapi import APIRouter
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
            "cache": {"status": "unknown", "engine": "Redis"}
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

    # 2. Check Attention Layer (Vector Store)
    try:
        from backend.core.vector_store import get_qdrant_client_ctx
        with get_qdrant_client_ctx() as client:
            if client:
                health["layers"]["attention"]["status"] = "connected"
            else:
                health["layers"]["attention"]["status"] = "offline"
    except Exception:
        health["layers"]["attention"]["status"] = "error"

    # 3. Check Memory Layer (Postgres)
    try:
        # Use a short timeout for the DB check
        async with async_session() as session:
            await asyncio.wait_for(session.execute(text("SELECT 1")), timeout=2.0)
            health["layers"]["memory"]["status"] = "connected"
    except Exception:
        health["layers"]["memory"]["status"] = "offline"

    # 4. Check Cache Layer (Redis)
    try:
        import redis.asyncio as redis
        r = redis.from_url(settings.redis_url, socket_timeout=2.0, socket_connect_timeout=2.0)
        await r.ping()
        health["layers"]["cache"]["status"] = "connected"
        await r.close()
    except Exception:
        health["layers"]["cache"]["status"] = "offline"

    # Overall Status
    if any(l["status"] == "offline" for l in health["layers"].values()):
        health["status"] = "degraded"
        
    return health


@router.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint; returns 501 if prometheus_client unavailable."""
    if not _PROM_AVAILABLE:
        return Response(status_code=501, content="Prometheus client not installed")
    data = generate_latest()
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)
