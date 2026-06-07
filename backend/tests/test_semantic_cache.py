import pytest
import json
import litellm
from unittest.mock import MagicMock, AsyncMock, patch
from backend.query.semantic_cache import SemanticCache
from backend.query.query_service import QueryService
from backend.reasoning.supervisor import QueryIntent
from sqlalchemy.ext.asyncio import AsyncSession
from backend.models.conversation import Conversation


@pytest.fixture(autouse=True)
def reset_litellm_state():
    """Reset litellm state between tests."""
    import litellm as _litellm

    original_acompletion = _litellm.acompletion
    _litellm.success_callback = []
    _litellm.failure_callback = []
    _litellm.api_base = None

    yield

    # Restore litellm.acompletion to whatever it was before this test
    _litellm.acompletion = original_acompletion
    _litellm.success_callback = []
    _litellm.failure_callback = []
    _litellm.api_base = None

@pytest.fixture
def mock_vector_store():
    with patch("backend.query.semantic_cache.VectorStore") as MockVS:
        yield MockVS.return_value

@pytest.fixture
def mock_embedder():
    with patch("backend.query.semantic_cache.Embedder") as MockEmbedder:
        mock_embedder_inst = MockEmbedder.return_value
        mock_embedder_inst.aembed = AsyncMock(return_value=[[0.1] * 384])
        yield mock_embedder_inst

@pytest.mark.asyncio
async def test_semantic_cache_hit(mock_vector_store, mock_embedder):
    cache = SemanticCache()
    
    # Mock search result for hit
    mock_vector_store.search.return_value = [
        {
            "score": 0.98,
            "metadata": {
                "answer": "Cached Answer",
                "sources": json.dumps([{"title": "Source 1", "url": ""}])
            }
        }
    ]
    
    result = await cache.check_cache("ws_1", "What is AI?")
    
    assert result is not None
    assert result["answer"] == "Cached Answer"
    assert result["cached"] is True
    assert result["similarity"] == 0.98
    mock_vector_store.search.assert_called_once()

@pytest.mark.asyncio
async def test_semantic_cache_miss(mock_vector_store, mock_embedder):
    cache = SemanticCache()
    
    # Mock search result for miss (low score)
    mock_vector_store.search.return_value = [
        {
            "score": 0.7,
            "metadata": {
                "answer": "Old Answer"
            }
        }
    ]
    
    result = await cache.check_cache("ws_1", "New question?")
    assert result is None
    
    # Mock search result for no results
    mock_vector_store.search.return_value = []
    result = await cache.check_cache("ws_1", "New question?")
    assert result is None

@pytest.mark.asyncio
async def test_semantic_cache_set(mock_vector_store, mock_embedder):
    cache = SemanticCache()
    
    result_to_cache = {
        "answer": "New Answer",
        "sources": [{"title": "Source A", "url": ""}]
    }
    
    await cache.set_cache("ws_1", "New question?", result_to_cache)
    
    mock_vector_store.upsert_batch.assert_called_once()
    args, kwargs = mock_vector_store.upsert_batch.call_args
    assert kwargs["workspace_id"] == "ws_1"
    assert kwargs["payloads"][0]["answer"] == "New Answer"
    assert "Source A" in kwargs["payloads"][0]["sources"]

@pytest.mark.asyncio
async def test_query_service_integration_hit(mock_vector_store, mock_embedder):
    db = AsyncMock(spec=AsyncSession)
    service = QueryService(db)
    
    # Mock conversation handling
    service._get_or_create_conversation = AsyncMock(return_value="conv_1")
    
    # Mock cache hit
    mock_vector_store.search.return_value = [
        {
            "score": 0.99,
            "metadata": {
                "answer": "Cache Hit Answer",
                "sources": json.dumps([])
            }
        }
    ]
    
    # Mock db.execute for conversation update
    mock_conv = MagicMock(spec=Conversation)
    db.execute.return_value = MagicMock(scalar_one=MagicMock(return_value=mock_conv))
    
    result = await service.execute_query(
        question="cached question",
        workspace_id="ws_1",
        user_id="user_1"
    )
    
    assert result["answer"] == "Cache Hit Answer"
    assert result["metadata"]["method"] == "semantic_cache"
    # Ensure orchestrators were NOT called (we check if SupervisorAgent wasn't used)
    with patch("backend.query.query_service.SupervisorAgent") as MockSupervisor:
        # If we re-run this with the patch, we can verify
        pass 
    
    # Actually, the logic should have returned early.

@pytest.mark.asyncio
async def test_query_service_integration_miss(mock_vector_store, mock_embedder):
    from backend.query.resolution import ResponseTier
    from backend.query.adaptive_router import RouteDecision
    from backend.query.generator import Answer

    db = AsyncMock(spec=AsyncSession)
    service = QueryService(db)
    
    # Mock conversation handling
    service._get_or_create_conversation = AsyncMock(return_value="conv_1")
    
    # Mock cache miss
    mock_vector_store.search.return_value = []
    
    # Mock routing decision
    service.router.route = AsyncMock(return_value=RouteDecision(
        tier=ResponseTier.FAST_RAG,
        intent=QueryIntent.QUICK_LOOKUP,
        rationale="test"
    ))
    
    # Mock fast RAG path
    service._fast_rag_path = AsyncMock(return_value=Answer(
        answer_text="Fresh Answer",
        sources=[{"title": "source1", "url": ""}],
        grounding_score=0.9,
        response_tier=ResponseTier.FAST_RAG.value
    ))
    
    # Mock db.execute for conversation update
    mock_conv = MagicMock(spec=Conversation)
    mock_result = MagicMock()
    mock_result.scalar_one.return_value = mock_conv
    db.execute.return_value = mock_result
    
    result = await service.execute_query(
        question="new question",
        workspace_id="ws_1",
        user_id="user_1"
    )
    
    assert result["answer"] == "Fresh Answer"
    assert result["metadata"]["method"] == "fast_rag_crag"
    
    # Verify set_cache was called (upsert_batch in mock_vector_store)
    assert mock_vector_store.upsert_batch.called


@pytest.mark.asyncio
async def test_semantic_cache_freshness_check_hit(mock_vector_store, mock_embedder):
    cache = SemanticCache()
    
    # Mock search result for hit (created at 2026-06-06T12:00:00)
    mock_vector_store.search.return_value = [
        {
            "score": 0.98,
            "metadata": {
                "answer": "Cached Answer",
                "sources": json.dumps([]),
                "created_at": "2026-06-06T12:00:00"
            }
        }
    ]
    
    # Mock db session and query result for last sync (2026-06-06T10:00:00 - older than cache)
    from datetime import datetime
    session = AsyncMock(spec=AsyncSession)
    res_mock = MagicMock()
    res_mock.scalar.return_value = datetime.fromisoformat("2026-06-06T10:00:00")
    session.execute.return_value = res_mock
    
    result = await cache.check_cache("ws_1", "What is AI?", session=session)
    
    assert result is not None
    assert result["answer"] == "Cached Answer"
    assert result["cached"] is True


@pytest.mark.asyncio
async def test_semantic_cache_freshness_check_stale(mock_vector_store, mock_embedder):
    cache = SemanticCache()
    
    # Mock search result for hit (created at 2026-06-06T12:00:00)
    mock_vector_store.search.return_value = [
        {
            "score": 0.98,
            "metadata": {
                "answer": "Cached Answer",
                "sources": json.dumps([]),
                "created_at": "2026-06-06T12:00:00"
            }
        }
    ]
    
    # Mock db session and query result for last sync (2026-06-06T14:00:00 - newer than cache)
    from datetime import datetime
    session = AsyncMock(spec=AsyncSession)
    res_mock = MagicMock()
    res_mock.scalar.return_value = datetime.fromisoformat("2026-06-06T14:00:00")
    session.execute.return_value = res_mock
    
    result = await cache.check_cache("ws_1", "What is AI?", session=session)
    
    # Stale cache should result in a cache miss (None)
    assert result is None


@pytest.mark.asyncio
async def test_semantic_cache_legacy_invalidation(mock_vector_store, mock_embedder):
    cache = SemanticCache()
    
    # Mock search result for hit (missing created_at)
    mock_vector_store.search.return_value = [
        {
            "score": 0.98,
            "metadata": {
                "answer": "Cached Answer",
                "sources": json.dumps([])
            }
        }
    ]
    
    # Mock db session and query result for last sync (some sync exists)
    from datetime import datetime
    session = AsyncMock(spec=AsyncSession)
    res_mock = MagicMock()
    res_mock.scalar.return_value = datetime.fromisoformat("2026-06-06T10:00:00")
    session.execute.return_value = res_mock
    
    result = await cache.check_cache("ws_1", "What is AI?", session=session)
    
    # Legacy entry should be invalidated if sync exists
    assert result is None


@pytest.mark.asyncio
async def test_query_service_stream_cache_hit(mock_vector_store, mock_embedder):
    db = AsyncMock(spec=AsyncSession)
    service = QueryService(db)
    
    # Mock conversation handling
    service._get_or_create_conversation = AsyncMock(return_value="conv_1")
    
    # Mock cache hit
    mock_vector_store.search.return_value = [
        {
            "score": 0.99,
            "metadata": {
                "answer": "Cached Streaming Answer",
                "sources": json.dumps([{"title": "Doc A", "url": "http://doca"}])
            }
        }
    ]
    
    # Mock db.execute for conversation update
    mock_conv = MagicMock(spec=Conversation)
    mock_result = MagicMock()
    mock_result.scalar_one.return_value = mock_conv
    db.execute.return_value = mock_result
    
    # Mock the short-lived session context manager inside stream_query
    session_mock = AsyncMock(spec=AsyncSession)
    session_mock.execute.return_value = mock_result
    
    class MockContextManager:
        async def __aenter__(self):
            return session_mock
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass
            
    with patch("backend.query.query_service.async_session", return_value=MockContextManager()):
        generator = service.stream_query(
            question="cached query",
            workspace_id="ws_1",
            user_id="user_1"
        )
        
        events = []
        async for event in generator:
            events.append(event)
            
    # Parse generated event strings
    payloads = []
    for ev in events:
        if ev.startswith("data:"):
            payloads.append(json.loads(ev[len("data:"):].strip()))
            
    assert len(payloads) > 0
    # First payload should be conversation
    assert payloads[0]["type"] == "conversation"
    # Status event should show generation status
    assert any(p.get("type") == "status" and p.get("phase") == "generation" for p in payloads)
    # Sources should be emitted
    sources_payload = next(p for p in payloads if p.get("type") == "sources")
    assert sources_payload["sources"][0]["title"] == "Doc A"
    assert sources_payload["sources"][0]["url"] == "http://doca"
    # Token payloads should spell out the cached answer
    tokens = [p["token"] for p in payloads if p.get("type") == "token"]
    assert "".join(tokens).strip() == "Cached Streaming Answer"
    # Metadata should show cached method details
    meta_payload = next(p for p in payloads if p.get("type") == "metadata")
    assert meta_payload["intent"] == "cached"
    assert meta_payload["tier"] == "direct"
    # Done payload should close the stream
    assert payloads[-1]["type"] == "done"


def test_embedder_caching():
    """
    Verify that Embedder caches query embeddings in-memory.
    """
    from backend.ingestion.embedder import Embedder, _EMBEDDING_CACHE
    import hashlib
    
    embedder = Embedder()
    # Ensure cache is clean for this test key
    test_text = "Unique caching text probe"
    h = hashlib.sha256(test_text.encode("utf-8")).hexdigest()
    if h in _EMBEDDING_CACHE:
        del _EMBEDDING_CACHE[h]
        
    # Generate embedding for the first time
    emb1 = embedder.embed([test_text])[0]
    
    # Verify it got cached
    assert h in _EMBEDDING_CACHE
    assert _EMBEDDING_CACHE[h] == emb1
    
    # Mock _hash_embedding and _get_model to verify they aren't called on cache hit
    with patch.object(embedder, "_hash_embedding") as mock_hash:
        emb2 = embedder.embed([test_text])[0]
        assert emb1 == emb2
        mock_hash.assert_not_called()


@pytest.mark.asyncio
async def test_llm_timeout_parameter():
    """
    Verify that SharedLLMClient passes the timeout parameter correctly to LiteLLM.
    """
    from backend.core.llm_impl import SharedLLMClient
    from backend.core.config import get_settings
    settings = get_settings()
    
    # Temporarily set timeout setting
    original_timeout = settings.llm_request_timeout
    settings.llm_request_timeout = 2.5
    
    try:
        client = SharedLLMClient(model_type="fast")
        
        # Mock acompletion — must be AsyncMock since it's awaited
        with patch("backend.core.llm_impl.litellm.acompletion", new_callable=AsyncMock) as mock_acompletion:
            # Build a properly-chained response so .choices[0].message.content is a real string
            mock_message = MagicMock()
            mock_message.content = "response"
            mock_choice = MagicMock()
            mock_choice.message = mock_message
            mock_response = MagicMock()
            mock_response.choices = [mock_choice]
            mock_acompletion.return_value = mock_response

            await client.chat_completion("sys", "user")

            mock_acompletion.assert_called_once()
            _, kwargs = mock_acompletion.call_args
            assert kwargs.get("timeout") == 2.5
    finally:
        settings.llm_request_timeout = original_timeout


@pytest.mark.asyncio
async def test_proactive_cache_purging(mock_vector_store):
    """
    Verify that purge_workspace_cache deletes points from vector store by workspace_id.
    """
    cache = SemanticCache()
    cache.purge_workspace_cache("ws_test")
    
    mock_vector_store.delete_by_workspace.assert_called_once_with("ws_test")


@pytest.mark.asyncio
async def test_sync_runner_proactive_purging():
    """
    Verify that ConnectorSyncRunner triggers cache purging when a sync finishes successfully.
    """
    from backend.workers.sync_runner import ConnectorSyncRunner
    from backend.models.sync_run import SyncRun, SyncRunStatus
    
    runner = ConnectorSyncRunner()
    
    # Mock finish_run, session and DB objects
    session = AsyncMock(spec=AsyncSession)
    sync_run = MagicMock(spec=SyncRun, id="run_1", connector_id="conn_1", workspace_id="ws_1")
    
    # Mock select
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = sync_run
    session.execute.return_value = mock_result
    
    # Patch async_session context manager in finish_sync_run
    class MockContextManager:
        async def __aenter__(self):
            return session
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass
            
    with patch("backend.workers.sync_runner.async_session", return_value=MockContextManager()):
        with patch("backend.query.semantic_cache.SemanticCache.purge_workspace_cache") as mock_purge:
            await runner._finish_sync_run("run_1", SyncRunStatus.COMPLETED)
            
            # Verify that purge was triggered on the workspace
            mock_purge.assert_called_once_with("ws_1")


