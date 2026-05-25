import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from sqlalchemy.ext.asyncio import AsyncSession
from backend.query.query_service import QueryService
from backend.reasoning.supervisor import QueryIntent
from backend.models.conversation import Conversation
from backend.models.query_log import QueryLog

@pytest.fixture
def mock_db():
    db = AsyncMock(spec=AsyncSession)
    return db

@pytest.fixture
def query_service(mock_db):
    return QueryService(mock_db)

@pytest.mark.asyncio
async def test_execute_query_conversational(query_service, mock_db):
    # Mock _get_or_create_conversation
    query_service._get_or_create_conversation = AsyncMock(return_value="00000000-0000-0000-0000-000000000000")
    
    # Mock SupervisorAgent
    with patch("backend.query.query_service.SupervisorAgent") as MockSupervisor:
        mock_supervisor = MockSupervisor.return_value
        mock_supervisor.classify_intent = AsyncMock(return_value=MagicMock(intent=QueryIntent.CONVERSATIONAL))
        
        # Mock db.execute for conversation update
        mock_conv = MagicMock(spec=Conversation)
        mock_db.execute.return_value = MagicMock(scalar_one=MagicMock(return_value=mock_conv))
        
        result = await query_service.execute_query(
            question="hello",
            workspace_id="test_ws",
            user_id="test_user"
        )
        
        assert result["answer"] == "I'm here to help you access your company's knowledge base. What would you like to know?"
        assert result["conversation_id"] == "00000000-0000-0000-0000-000000000000"
        assert result["metadata"]["intent"] == QueryIntent.CONVERSATIONAL.value

@pytest.mark.asyncio
async def test_execute_query_quick_lookup(query_service, mock_db):
    query_service._get_or_create_conversation = AsyncMock(return_value="00000000-0000-0000-0000-000000000000")
    
    with patch("backend.query.query_service.SupervisorAgent") as MockSupervisor, \
         patch("backend.query.query_service.QuickRetrieverAgent") as MockAgent:
        
        mock_supervisor = MockSupervisor.return_value
        mock_supervisor.classify_intent = AsyncMock(return_value=MagicMock(intent=QueryIntent.QUICK_LOOKUP))
        
        mock_agent = MockAgent.return_value
        mock_agent.execute = AsyncMock(return_value={
            "answer": "Test Answer",
            "sources": ["source1"],
            "confidence": 0.9
        })
        
        # Mock db.execute for conversation update
        mock_conv = MagicMock(spec=Conversation)
        mock_db.execute.return_value = MagicMock(scalar_one=MagicMock(return_value=mock_conv))
        
        result = await query_service.execute_query(
            question="test question",
            workspace_id="test_ws",
            user_id="test_user"
        )
        
        assert result["answer"] == "Test Answer"
        assert result["sources"] == [{"title": "source1", "url": ""}]
        assert result["metadata"]["intent"] == QueryIntent.QUICK_LOOKUP.value

@pytest.mark.asyncio
async def test_stream_query_conversational(query_service):
    query_service._get_or_create_conversation = AsyncMock(return_value="00000000-0000-0000-0000-000000000000")
    
    with patch("backend.query.query_service.SupervisorAgent") as MockSupervisor:
        mock_supervisor = MockSupervisor.return_value
        mock_supervisor.classify_intent = AsyncMock(return_value=MagicMock(intent=QueryIntent.CONVERSATIONAL))
        
        events = []
        async for event in query_service.stream_query(
            question="hello",
            workspace_id="test_ws",
            user_id="test_user"
        ):

            events.append(event)
            
        assert any("Analyzing query intent..." in e for e in events)
        assert any("Intent classified as: conversational" in e for e in events)
        assert any("I'm here to help you access your company's knowledge base" in e for e in events)
