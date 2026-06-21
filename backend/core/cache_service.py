"""
Assest — Multi-Tier Cache Service

L1: Redis exact-match hot cache (sub-5ms)
L2: Qdrant semantic similarity cache (sub-50ms)

Falls through gracefully when Redis is unavailable.
"""

import hashlib
import json
import logging
from typing import Any, Dict, List, Optional

from backend.core.config import get_settings
from backend.core.redis_client import get_redis
from backend.query.semantic_cache import SemanticCache

logger = logging.getLogger(__name__)
settings = get_settings()

CACHE_VERSION = "v1"
DEFAULT_TTL_SECONDS = 300


def _normalize_question(question: str) -> str:
    """Normalize question text for stable cache keys."""
    return " ".join(question.lower().strip().split())


def _cache_key(workspace_id: str, question: str, context_files: Optional[List[str]] = None) -> str:
    """Build a deterministic L1 cache key."""
    normalized = _normalize_question(question)
    if context_files:
        normalized += ":" + ",".join(sorted(context_files))
    digest = hashlib.sha256(normalized.encode()).hexdigest()[:16]
    return f"cache:{CACHE_VERSION}:{workspace_id}:{digest}"
 
 
class CacheService:
    """
    Orchestrates L1 (Redis) and L2 (semantic/Qdrant) caching tiers.
 
    Read path:  L1 → L2 → None (caller runs full RAG)
    Write path: L1 + L2 (best-effort, never raises)
    """
 
    def __init__(self, semantic_cache: Optional[SemanticCache] = None):
        self._semantic = semantic_cache or SemanticCache()
 
    async def get(
        self,
        workspace_id: str,
        question: str,
        session: Optional[Any] = None,
        *,
        skip_semantic: bool = False,
        context_files: Optional[List[str]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Check L1 then L2 cache tiers. Returns cached result dict or None.
        """
        l1_hit = await self._get_l1(workspace_id, question, context_files)
        if l1_hit is not None:
            l1_hit["cache_tier"] = "L1"
            return l1_hit
 
        if skip_semantic:
            return None
 
        l2_hit = await self._semantic.check_cache(workspace_id, question, session=session, context_files=context_files)
        if l2_hit is not None:
            l2_hit["cache_tier"] = "L2"
            await self._set_l1(workspace_id, question, l2_hit, context_files=context_files)
            return l2_hit
 
        return None
 
    async def set(
        self,
        workspace_id: str,
        question: str,
        result: Dict[str, Any],
        *,
        skip_semantic: bool = False,
        context_files: Optional[List[str]] = None,
    ) -> None:
        """
        Write result to both cache tiers (best-effort).
        """
        await self._set_l1(workspace_id, question, result, context_files=context_files)
 
        if not skip_semantic:
            try:
                await self._semantic.set_cache(workspace_id, question, result, context_files=context_files)
            except Exception as exc:
                logger.warning("L2 cache write failed: %s", exc)
 
    async def invalidate_workspace(self, workspace_id: str) -> int:
        """
        Purge all L1 keys for a workspace. Also purges L2 semantic cache.
        Returns count of L1 keys deleted.
        """
        deleted = await self._purge_l1_workspace(workspace_id)
 
        try:
            self._semantic.purge_workspace_cache(workspace_id)
        except Exception as exc:
            logger.warning("L2 cache purge failed: %s", exc)
 
        return deleted
 
    async def _get_l1(self, workspace_id: str, question: str, context_files: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
        redis = await get_redis()
        if redis is None:
            return None
 
        key = _cache_key(workspace_id, question, context_files)
        try:
            raw = await redis.get(key)
            if raw is None:
                return None
 
            data = json.loads(raw)
            data["cached"] = True
            logger.debug("L1 cache hit: workspace=%s", workspace_id)
            return data
        except Exception as exc:
            logger.warning("L1 cache read error: %s", exc)
            return None
 
    async def _set_l1(
        self,
        workspace_id: str,
        question: str,
        result: Dict[str, Any],
        ttl: int = DEFAULT_TTL_SECONDS,
        context_files: Optional[List[str]] = None,
    ) -> None:
        redis = await get_redis()
        if redis is None:
            return
 
        key = _cache_key(workspace_id, question, context_files)
        payload = {
            "answer": result.get("answer"),
            "sources": result.get("sources", []),
            "cached": True,
        }
        try:
            await redis.setex(key, ttl, json.dumps(payload))
        except Exception as exc:
            logger.warning("L1 cache write error: %s", exc)

    async def _purge_l1_workspace(self, workspace_id: str) -> int:
        redis = await get_redis()
        if redis is None:
            return 0

        pattern = f"cache:{CACHE_VERSION}:{workspace_id}:*"
        deleted = 0
        try:
            async for key in redis.scan_iter(match=pattern, count=100):
                await redis.delete(key)
                deleted += 1
        except Exception as exc:
            logger.warning("L1 cache purge error: %s", exc)

        logger.info("Purged %d L1 cache keys for workspace %s", deleted, workspace_id)
        return deleted
