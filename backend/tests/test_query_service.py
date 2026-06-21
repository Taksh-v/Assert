import pytest
import json
from unittest.mock import MagicMock, AsyncMock, patch
from sqlalchemy.ext.asyncio import AsyncSession
from backend.query.query_service import QueryService
from backend.reasoning.supervisor import QueryIntent
from backend.models.conversation import Conversation
from backend.models.query_log import QueryLog
from backend.query.resolution import ResponseTier
from backend.query.adaptive_router import RouteDecision
from backend.query.generator import Answer

@pytest.fixture
def mock_db():
    db = AsyncMock(spec=AsyncSession)
    return db

@pytest.fixture
def query_service(mock_db):
    qs = QueryService(mock_db)
    qs.retriever.search = AsyncMock(return_value=[])
    qs.cache.get = AsyncMock(return_value=None)
    qs._should_run_quality_eval = MagicMock(return_value=False)
    return qs

@pytest.mark.asyncio
async def test_execute_query_conversational(query_service, mock_db):
    # Mock _get_or_create_conversation
    query_service._get_or_create_conversation = AsyncMock(return_value="00000000-0000-0000-0000-000000000000")
    
    # Mock routing decision
    query_service.router.route = AsyncMock(return_value=RouteDecision(
        tier=ResponseTier.DIRECT,
        intent=QueryIntent.CONVERSATIONAL,
        rationale="Simple greeting or acknowledgment detected",
        skip_retrieval=True
    ))
    
    # Mock generator direct response
    query_service.generator.generate_direct_response = AsyncMock(return_value=Answer(
        answer_text="Hello! How can I help you today?",
        sources=[],
        response_tier=ResponseTier.DIRECT.value
    ))
    
    # Mock db.execute for history load and conversation update
    mock_conv = MagicMock(spec=Conversation)
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_result.scalar_one.return_value = mock_conv
    mock_db.execute.return_value = mock_result
    
    result = await query_service.execute_query(
        question="hello",
        workspace_id="test_ws",
        user_id="test_user"
    )
    
    assert result["answer"] == "Hello! How can I help you today?"
    assert result["conversation_id"] == "00000000-0000-0000-0000-000000000000"
    assert result["metadata"]["intent"] == QueryIntent.CONVERSATIONAL.value
    assert result["response_tier"] == ResponseTier.DIRECT.value


@pytest.mark.asyncio
async def test_execute_query_quick_lookup(query_service, mock_db):
    query_service._get_or_create_conversation = AsyncMock(return_value="00000000-0000-0000-0000-000000000000")
    
    # Mock routing decision
    query_service.router.route = AsyncMock(return_value=RouteDecision(
        tier=ResponseTier.FAST_RAG,
        intent=QueryIntent.QUICK_LOOKUP,
        rationale="Retrieval required"
    ))
    
    # Mock fast RAG path
    query_service._fast_rag_path = AsyncMock(return_value=Answer(
        answer_text="Test Answer",
        sources=[{"title": "source1", "url": ""}],
        grounding_score=0.9,
        response_tier=ResponseTier.FAST_RAG.value
    ))
    
    # Mock db.execute for history load and conversation update
    mock_conv = MagicMock(spec=Conversation)
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_result.scalar_one.return_value = mock_conv
    mock_db.execute.return_value = mock_result
    
    result = await query_service.execute_query(
        question="test question",
        workspace_id="test_ws",
        user_id="test_user"
    )
    
    assert result["answer"] == "Test Answer"
    assert result["sources"] == [{"title": "source1", "url": ""}]
    assert result["metadata"]["intent"] == QueryIntent.QUICK_LOOKUP.value
    assert result["response_tier"] == ResponseTier.FAST_RAG.value


@pytest.mark.asyncio
async def test_stream_query_conversational(query_service, mock_db):
    query_service._get_or_create_conversation = AsyncMock(return_value="00000000-0000-0000-0000-000000000000")
    
    # Mock routing decision
    query_service.router.route = AsyncMock(return_value=RouteDecision(
        tier=ResponseTier.DIRECT,
        intent=QueryIntent.CONVERSATIONAL,
        rationale="Simple greeting or acknowledgment detected",
        skip_retrieval=True
    ))
    
    # Mock db.execute for history load and conversation update
    mock_conv = MagicMock(spec=Conversation)
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_result.scalar_one.return_value = mock_conv
    mock_db.execute.return_value = mock_result
    
    async def mock_stream_chat(*args, **kwargs):
        yield f"data: {json.dumps({'type': 'token', 'token': 'Hello '})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
    
    with patch("backend.query.query_service.StreamGenerator") as MockSG:
        MockSG.return_value.stream_chat = mock_stream_chat
        
        events = []
        async for event in query_service.stream_query(
            question="hello",
            workspace_id="test_ws",
            user_id="test_user"
        ):
            events.append(event)
            
        assert any("Analyzing query intent..." in e for e in events)
        assert any("Route: direct (conversational)" in e for e in events)
        assert any('"token": "Hello "' in e for e in events)


@pytest.mark.asyncio
async def test_execute_query_metadata_count(query_service, mock_db):
    query_service._get_or_create_conversation = AsyncMock(return_value="00000000-0000-0000-0000-000000000000")

    # Mock the count database results
    mock_conv = MagicMock(spec=Conversation)
    mock_result_count = MagicMock()
    mock_result_count.scalar.return_value = 5

    mock_result_docs = MagicMock()
    mock_result_docs.all.return_value = [("Doc1", "http://doc1"), ("Doc2", "http://doc2")]
    mock_result_docs.scalar_one.return_value = mock_conv

    # Implicit context files resolution result (resolves recent doc titles)
    mock_implicit_ctx = MagicMock()
    mock_implicit_ctx.all.return_value = [("Doc1",), ("Doc2",)]

    # Sequence of database execute results:
    # 1. implicit context files query (vague query resolves recent docs)
    # 2. workspace role query
    # 3. count query execution
    # 4. doc list query execution
    # 5. load conversation (to update updated_at)
    mock_role_res = MagicMock()
    mock_role_res.scalar.return_value = "employee"
    mock_db.execute.side_effect = [mock_implicit_ctx, mock_role_res, mock_result_count, mock_result_docs, mock_result_docs]

    result = await query_service.execute_query(
        question="how many documents are in the system?",
        workspace_id="test_ws",
        user_id="test_user"
    )

    assert "currently 5 active documents" in result["answer"]
    assert result["sources"] == [{"title": "Doc1", "url": "http://doc1"}, {"title": "Doc2", "url": "http://doc2"}]
    assert result["response_tier"] == ResponseTier.DIRECT.value
    assert result["metadata"]["method"] == "system_metadata_query"


@pytest.mark.asyncio
async def test_execute_query_metadata_list(query_service, mock_db):
    query_service._get_or_create_conversation = AsyncMock(return_value="00000000-0000-0000-0000-000000000000")

    # Mock the count database results
    mock_conv = MagicMock(spec=Conversation)
    mock_result_count = MagicMock()
    mock_result_count.scalar.return_value = 2

    mock_result_docs = MagicMock()
    mock_result_docs.all.return_value = [("Doc1", "http://doc1"), ("Doc2", "http://doc2")]
    mock_result_docs.scalar_one.return_value = mock_conv

    # Implicit context files resolution result (resolves recent doc titles)
    mock_implicit_ctx = MagicMock()
    mock_implicit_ctx.all.return_value = [("Doc1",), ("Doc2",)]

    # Sequence: implicit_ctx → role → count → docs → conversation_update
    mock_role_res = MagicMock()
    mock_role_res.scalar.return_value = "employee"
    mock_db.execute.side_effect = [mock_implicit_ctx, mock_role_res, mock_result_count, mock_result_docs, mock_result_docs]

    result = await query_service.execute_query(
        question="show all documents",
        workspace_id="test_ws",
        user_id="test_user"
    )

    assert "Here are the 2 active documents" in result["answer"]
    assert "- [Doc1](http://doc1)" in result["answer"]
    assert result["sources"] == [{"title": "Doc1", "url": "http://doc1"}, {"title": "Doc2", "url": "http://doc2"}]
    assert result["response_tier"] == ResponseTier.DIRECT.value

