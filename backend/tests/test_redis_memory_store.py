import asyncio
import pytest

from backend.memory import redis_store


@pytest.mark.asyncio
async def test_redis_memory_store_skip_if_unavailable():
    # Skip if redis.asyncio is not installed
    if getattr(redis_store, "aioredis", None) is None:
        pytest.skip("redis.asyncio not installed")

    try:
        store = redis_store.RedisMemoryStore()
    except Exception:
        pytest.skip("Redis not available or connection refused")

    # quick ping check with timeout
    try:
        await asyncio.wait_for(store._redis.ping(), timeout=0.5)
    except Exception:
        await store.close()
        pytest.skip("Redis ping failed")

    await store.set("x", {"v": 1})
    assert await store.get("x") == {"v": 1}
    snap = await store.snapshot()
    assert "x" in snap
    await store.delete("x")
    assert await store.get("x") is None
    await store.restore(snap)
    assert await store.get("x") == {"v": 1}
    await store.close()
