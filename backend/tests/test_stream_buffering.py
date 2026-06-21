import pytest
import json
import uuid
from unittest.mock import MagicMock, AsyncMock, patch
from sqlalchemy.ext.asyncio import AsyncSession
from backend.query.query_service import QueryService
from backend.query.resolution import ResponseTier
from backend.reasoning.supervisor import QueryIntent
from backend.query.adaptive_router import RouteDecision

@pytest.fixture
def mock_db():
    db = AsyncMock(spec=AsyncSession)
    return db

@pytest.fixture
def query_service(mock_db):
    qs = QueryService(mock_db)
    qs.retriever.search = AsyncMock(return_value=[])
    qs.cache.get = AsyncMock(return_value=None)
    qs._should_run_quality_eval = MagicMock(return_value=True) # Enable to test bypass
    return qs

@pytest.mark.asyncio
async def test_stream_query_buffering_behavior(query_service):
    # Mock _stream_query_raw to yield specific chunks
    async def mock_raw(*args, **kwargs):
        # We will yield token events, status events, and done events
        req_id = kwargs.get("request_id", "test-req-id")
        yield f"data: {json.dumps({'type': 'status', 'status': 'Starting...', 'phase': 'routing', 'request_id': req_id})}\n\n"
        yield f"data: {json.dumps({'type': 'token', 'token': 'First', 'request_id': req_id})}\n\n"
        yield f"data: {json.dumps({'type': 'token', 'token': 'Second', 'request_id': req_id})}\n\n"
        yield f"data: {json.dumps({'type': 'token', 'token': 'Third', 'request_id': req_id})}\n\n"
        yield f"data: {json.dumps({'type': 'token', 'token': 'Fourth', 'request_id': req_id})}\n\n"
        yield f"data: {json.dumps({'type': 'token', 'token': 'Fifth', 'request_id': req_id})}\n\n"
        yield f"data: {json.dumps({'type': 'token', 'token': 'Sixth.', 'request_id': req_id})}\n\n"
        yield f"data: {json.dumps({'type': 'token', 'token': 'Seventh', 'request_id': req_id})}\n\n"
        yield f"data: {json.dumps({'type': 'done', 'request_id': req_id})}\n\n"

    query_service._stream_query_raw = mock_raw

    chunks = []
    async for chunk in query_service.stream_query(
        question="test question",
        workspace_id="test_ws",
        user_id="test_user",
        request_id="test-req-id"
    ):
        chunks.append(chunk)

    # Let's inspect the chunks yielded:
    # 1. status: Starting...
    # 2. 'First' (first token, yielded immediately)
    # 3. 'SecondThirdFourthFifth' (batched 4 tokens: Second, Third, Fourth, Fifth)
    # 4. 'Sixth.' (has punctuation, flushed immediately)
    # 5. 'Seventh' (flushed on next non-token event: done)
    # 6. done
    
    # Parse chunks to payloads
    payloads = []
    for chunk in chunks:
        if chunk.startswith("data:"):
            payloads.append(json.loads(chunk[5:].strip()))

    # Verify order of events
    assert payloads[0]["type"] == "status"
    assert payloads[0]["status"] == "Starting..."

    # First token yielded immediately
    assert payloads[1]["type"] == "token"
    assert payloads[1]["token"] == "First"

    # Second, Third, Fourth, Fifth accumulated (4 tokens total) and flushed
    assert payloads[2]["type"] == "token"
    assert payloads[2]["token"] == "SecondThirdFourthFifth"

    # Sixth. flushed because it contains punctuation
    assert payloads[3]["type"] == "token"
    assert payloads[3]["token"] == "Sixth."

    # Seventh flushed when done event occurs
    assert payloads[4]["type"] == "token"
    assert payloads[4]["token"] == "Seventh"

    # Done event
    assert payloads[5]["type"] == "done"


@pytest.mark.asyncio
async def test_stream_query_direct_bypass_eval(query_service, mock_db):
    # Mock conversation thread and query router
    query_service._get_or_create_conversation = AsyncMock(return_value="00000000-0000-0000-0000-000000000000")
    query_service.router.route = AsyncMock(return_value=RouteDecision(
        tier=ResponseTier.DIRECT,
        intent=QueryIntent.CONVERSATIONAL,
        rationale="Simple direct path",
        skip_retrieval=True
    ))

    # Mock conversation database calls
    mock_conv = MagicMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_result.scalar_one.return_value = mock_conv
    mock_db.execute.return_value = mock_result

    # Mock StreamGenerator so it does not actually call API
    async def mock_stream_chat(*args, **kwargs):
        yield f"data: {json.dumps({'type': 'token', 'token': 'Hello', 'request_id': 'test-req-id'})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    with patch("backend.query.query_service.StreamGenerator") as MockSG:
        MockSG.return_value.stream_chat = mock_stream_chat

        # We will collect events from stream_query
        events = []
        async for event in query_service.stream_query(
            question="hello",
            workspace_id="test_ws",
            user_id="test_user",
            request_id="test-req-id"
        ):
            events.append(event)

        # Parse payloads
        metadata_payload = None
        for event in events:
            if "metadata" in event:
                metadata_payload = json.loads(event[5:].strip())
                break

        assert metadata_payload is not None
        # Verify that quality evaluation was skipped by checking faithfulness_score and relevance_score are both 1.0,
        # and eval_reasoning matches the skipped by policy format.
        assert metadata_payload["faithfulness_score"] == 1.0
        assert metadata_payload["relevance_score"] == 1.0
        assert "skipped by policy" in metadata_payload["eval_reasoning"].lower()
