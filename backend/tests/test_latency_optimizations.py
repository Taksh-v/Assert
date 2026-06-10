import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from backend.query.adaptive_router import AdaptiveRouter, _ROUTE_CACHE, RouteDecision
from backend.query.resolution import ResponseTier
from backend.reasoning.supervisor import QueryIntent
from backend.query.query_service import QueryService
from backend.core.database import async_session


@pytest.mark.asyncio
async def test_router_caching_and_heuristics():
    """
    Verify that:
    1. Common question words map directly to FAST_RAG (bypassing LLM calls).
    2. Decisions are cached in _ROUTE_CACHE for sub-millisecond retrieval on repeat queries.
    """
    router = AdaptiveRouter()
    
    # 1. Clear the cache first to ensure a clean state
    _ROUTE_CACHE.clear()

    # 2. Test common question words shortcut (e.g. "how to connect slack")
    decision1 = await router.route("how to connect slack")
    assert decision1.tier == ResponseTier.FAST_RAG
    assert decision1.intent == QueryIntent.QUICK_LOOKUP
    assert "heuristic" in decision1.rationale.lower()

    # 3. Test caching: Verify subsequent call uses cache
    cache_key = "how to connect slack:False"
    assert cache_key in _ROUTE_CACHE
    
    # Modify cache entry to verify routing returns the cached object
    _ROUTE_CACHE[cache_key] = RouteDecision(
        tier=ResponseTier.DIRECT,
        intent=QueryIntent.CONVERSATIONAL,
        rationale="Cached Mock Value"
    )

    decision2 = await router.route("how to connect slack")
    assert decision2.tier == ResponseTier.DIRECT
    assert decision2.rationale == "Cached Mock Value"


@pytest.mark.asyncio
async def test_optimized_streaming_cache_hits():
    """
    Verify that query streaming on a cache hit yields chunked tokens immediately
    without blocking word-by-word with long artificial sleep delays.
    """
    query_service = QueryService(None)
    
    # Mock cache hit returning a multi-word answer
    mock_cache = AsyncMock()
    mock_cache.check_cache.return_value = {
        "answer": "This is a long test response containing multiple words to verify chunking behavior.",
        "sources": [{"title": "Doc 1", "url": "https://doc1.com"}],
        "similarity": 0.95
    }
    query_service.cache = mock_cache

    # Mock DB commit
    mock_db = MagicMock()
    query_service.db = mock_db

    # Stream the query
    stream = query_service.stream_query(
        question="test question",
        workspace_id="ws123",
        user_id="u123",
        conversation_id="conv123",
        reasoning_mode=False,
        request_id="req123"
    )

    chunks = []
    # Use patch to verify sleep was only called a few times (for 15-word chunks)
    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep, \
         patch("backend.query.query_service.async_session") as mock_session_ctx:
        
        # Mock DB async context manager
        mock_session = AsyncMock()
        mock_session_ctx.return_value.__aenter__.return_value = mock_session

        async for chunk in stream:
            chunks.append(chunk)

        # Confirm tokens were yielded and sleep was called only once (for 13 words chunked into 1)
        assert len(chunks) > 0
        mock_sleep.assert_called_once()
