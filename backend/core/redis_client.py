"""
Assest — Redis Connection Pool

Singleton async Redis client with connection pooling.
Gracefully degrades when Redis is unavailable (cache becomes no-op).
"""

import logging
from typing import Optional

try:
    import redis.asyncio as aioredis
except ImportError:  # pragma: no cover
    aioredis = None

from backend.core.config import get_settings

logger = logging.getLogger(__name__)

_redis_client: Optional["aioredis.Redis"] = None
_redis_available: bool = True


async def get_redis() -> Optional["aioredis.Redis"]:
    """
    Return the shared Redis client, or None if Redis is unavailable.
    """
    global _redis_client, _redis_available

    if not _redis_available or aioredis is None:
        return None

    if _redis_client is None:
        settings = get_settings()
        try:
            _redis_client = aioredis.from_url(
                settings.redis_url,
                decode_responses=True,
                max_connections=20,
                socket_connect_timeout=2,
                socket_timeout=2,
                retry_on_timeout=True,
            )
            await _redis_client.ping()
            logger.info("Redis connected: %s", settings.redis_url.split("@")[-1])
        except Exception as exc:
            logger.warning("Redis unavailable, caching disabled: %s", exc)
            _redis_available = False
            _redis_client = None
            return None

    return _redis_client


async def close_redis() -> None:
    """Dispose the Redis connection pool on shutdown."""
    global _redis_client, _redis_available

    if _redis_client is not None:
        try:
            aclose = getattr(_redis_client, "aclose", None)
            if aclose is not None:
                await aclose()
            else:
                await _redis_client.close()
        except Exception as exc:
            logger.debug("Redis close error (ignored): %s", exc)
        finally:
            _redis_client = None

    _redis_available = True


async def redis_health_check() -> dict:
    """
    Ping Redis and return status dict for /health endpoint.
    """
    client = await get_redis()
    if client is None:
        return {"status": "offline", "engine": "Redis"}

    try:
        latency_ms = await _measure_ping_ms(client)
        return {"status": "connected", "engine": "Redis", "latency_ms": latency_ms}
    except Exception as exc:
        return {"status": f"offline: {exc}", "engine": "Redis"}


async def _measure_ping_ms(client: "aioredis.Redis") -> float:
    import time

    start = time.monotonic()
    await client.ping()
    return round((time.monotonic() - start) * 1000, 2)
