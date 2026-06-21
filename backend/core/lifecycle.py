"""
Assest — Application Lifecycle Management

Centralizes startup/shutdown for all external dependencies.
Called from FastAPI lifespan in main.py.
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from backend.core.config import get_settings
from backend.core.database import init_db, close_db
from backend.core.redis_client import get_redis, close_redis, redis_health_check

logger = logging.getLogger(__name__)


async def startup() -> None:
    """
    Warm up all dependencies in parallel where possible.
    Failures in optional deps (Redis) are logged but do not block startup.
    """
    settings = get_settings()
    logger.info("Assest Brain starting (env=%s, version=%s)", settings.app_env, settings.app_version)

    await init_db()
    logger.info("Database initialized")

    # Warm up Qdrant collections and self-heal if necessary
    try:
        from backend.core.vector_store import initialize_qdrant_collections
        initialize_qdrant_collections()
        logger.info("Qdrant collections initialized/warmed up")
    except Exception as e:
        logger.error("Failed to warm up Qdrant collections: %s", e)

    # Warm up sparse indexer
    try:
        from backend.query.sparse_indexer import get_sparse_indexer
        await get_sparse_indexer().load_from_sqlite()
        logger.info("BM25 sparse indexer loaded")
    except Exception as e:
        logger.error("Failed to load BM25 index on startup: %s", e)

    redis_status = await redis_health_check()
    if redis_status["status"] == "connected":
        logger.info("Redis ready (latency=%sms)", redis_status.get("latency_ms"))
    else:
        logger.warning("Redis not available — L1 cache disabled")

    if settings.enable_workers:
        logger.info("Background workers enabled (configured via worker_main.py)")

    if settings.enable_prometheus:
        logger.info("Prometheus metrics enabled on port %s", settings.prometheus_port)

    logger.info("Startup complete")


async def shutdown() -> None:
    """Gracefully release all connection pools."""
    logger.info("Assest Brain shutting down...")
    await close_redis()
    await close_db()
    logger.info("Shutdown complete")


@asynccontextmanager
async def app_lifespan(_app) -> AsyncGenerator[None, None]:
    """FastAPI lifespan context manager."""
    await startup()
    yield
    await shutdown()
