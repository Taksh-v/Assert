"""Tests for multi-tier CacheService."""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from backend.core.cache_service import CacheService, _cache_key, _normalize_question


@pytest.fixture
def mock_semantic():
    semantic = MagicMock()
    semantic.check_cache = AsyncMock(return_value=None)
    semantic.set_cache = AsyncMock()
    semantic.purge_workspace_cache = MagicMock()
    return semantic


@pytest.fixture
def mock_redis():
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.setex = AsyncMock()
    redis.delete = AsyncMock()
    redis.scan_iter = AsyncMock(return_value=iter([]))
    return redis


@pytest.mark.asyncio
async def test_cache_key_is_deterministic():
    q1 = _cache_key("ws1", "What is our refund policy?")
    q2 = _cache_key("ws1", "  WHAT IS OUR REFUND POLICY?  ")
    assert q1 == q2
    assert q1.startswith("cache:v1:ws1:")


@pytest.mark.asyncio
async def test_normalize_question():
    assert _normalize_question("  Hello   World  ") == "hello world"


@pytest.mark.asyncio
async def test_l1_cache_hit(mock_semantic, mock_redis):
    l1_payload = {"answer": "Fast answer", "sources": [{"title": "Doc", "url": ""}]}
    mock_redis.get = AsyncMock(return_value=json.dumps(l1_payload))

    with patch("backend.core.cache_service.get_redis", AsyncMock(return_value=mock_redis)):
        cache = CacheService(semantic_cache=mock_semantic)
        result = await cache.get("ws1", "test question")

    assert result is not None
    assert result["answer"] == "Fast answer"
    assert result["cache_tier"] == "L1"
    mock_semantic.check_cache.assert_not_called()


@pytest.mark.asyncio
async def test_l2_cache_hit_populates_l1(mock_semantic, mock_redis):
    l2_payload = {
        "answer": "Semantic answer",
        "sources": [],
        "cached": True,
        "similarity": 0.97,
    }
    mock_semantic.check_cache = AsyncMock(return_value=l2_payload)

    with patch("backend.core.cache_service.get_redis", AsyncMock(return_value=mock_redis)):
        cache = CacheService(semantic_cache=mock_semantic)
        result = await cache.get("ws1", "test question")

    assert result is not None
    assert result["cache_tier"] == "L2"
    mock_redis.setex.assert_called_once()


@pytest.mark.asyncio
async def test_cache_miss_returns_none(mock_semantic, mock_redis):
    with patch("backend.core.cache_service.get_redis", AsyncMock(return_value=mock_redis)):
        cache = CacheService(semantic_cache=mock_semantic)
        result = await cache.get("ws1", "unknown question")

    assert result is None


@pytest.mark.asyncio
async def test_set_writes_both_tiers(mock_semantic, mock_redis):
    with patch("backend.core.cache_service.get_redis", AsyncMock(return_value=mock_redis)):
        cache = CacheService(semantic_cache=mock_semantic)
        await cache.set("ws1", "question", {"answer": "A", "sources": []})

    mock_redis.setex.assert_called_once()
    mock_semantic.set_cache.assert_called_once()


@pytest.mark.asyncio
async def test_graceful_degradation_without_redis(mock_semantic):
    with patch("backend.core.cache_service.get_redis", AsyncMock(return_value=None)):
        cache = CacheService(semantic_cache=mock_semantic)
        result = await cache.get("ws1", "question")

    mock_semantic.check_cache.assert_called_once()
    assert result is None


@pytest.mark.asyncio
async def test_invalidate_workspace(mock_semantic, mock_redis):
    keys = ["cache:v1:ws1:abc", "cache:v1:ws1:def"]

    async def _scan(*args, **kwargs):
        for k in keys:
            yield k

    mock_redis.scan_iter = _scan

    with patch("backend.core.cache_service.get_redis", AsyncMock(return_value=mock_redis)):
        cache = CacheService(semantic_cache=mock_semantic)
        deleted = await cache.invalidate_workspace("ws1")

    assert deleted == 2
    mock_semantic.purge_workspace_cache.assert_called_once_with("ws1")
