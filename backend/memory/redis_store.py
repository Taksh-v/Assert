import json
from typing import Any, Dict, Optional

try:
    import redis.asyncio as aioredis
except Exception:  # pragma: no cover - not installed in some envs
    aioredis = None


class RedisMemoryStore:
    """Redis-backed MemoryStore implementation.

    Uses a simple namespaced key prefix. Values are JSON-serialized.
    This implementation is tolerant of missing `redis.asyncio` at import
    time so tests can skip when the dependency isn't present.
    """

    name = "redis"

    def __init__(self, redis_url: str = "redis://localhost:6379/0", namespace: str = "memstore") -> None:
        if aioredis is None:
            raise RuntimeError("redis.asyncio is not installed")
        self._redis = aioredis.from_url(redis_url, decode_responses=True)
        self._ns = namespace

    def _key(self, key: str) -> str:
        return f"{self._ns}:{key}"

    async def set(self, key: str, value: Any) -> None:
        await self._redis.set(self._key(key), json.dumps(value))

    async def get(self, key: str) -> Optional[Any]:
        raw = await self._redis.get(self._key(key))
        if raw is None:
            return None
        return json.loads(raw)

    async def delete(self, key: str) -> None:
        await self._redis.delete(self._key(key))

    async def snapshot(self) -> Dict[str, Any]:
        # gather keys with the namespace prefix
        rv: Dict[str, Any] = {}
        cursor = b"0"
        # redis.asyncio supports scan_iter
        async for full in self._redis.scan_iter(f"{self._ns}:*"):
            raw = await self._redis.get(full)
            if raw is None:
                continue
            # strip namespace
            key = full[len(self._ns) + 1 :]
            rv[key] = json.loads(raw)
        return rv

    async def restore(self, snapshot: Dict[str, Any]) -> None:
        if not snapshot:
            return
        async with self._redis.pipeline() as pipe:
            for k, v in snapshot.items():
                await pipe.set(self._key(k), json.dumps(v))
            await pipe.execute()

    async def close(self) -> None:
        try:
            # prefer the async aclose() when available in newer clients
            aclose = getattr(self._redis, "aclose", None)
            if aclose is not None:
                await aclose()
            else:
                await self._redis.close()
        except Exception:
            pass
