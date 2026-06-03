"""
Direct E2E verification of the query route logic.
Bypasses FastAPI TestClient to test the query pipeline directly using a real SQLite session.
"""
import sys
import asyncio
from unittest.mock import MagicMock, AsyncMock

print("[DEBUG] Setting up sys.modules mocks...")
# Mock dependencies
mock_passlib = MagicMock()
mock_passlib.context = MagicMock()
mock_passlib.context.CryptContext = MagicMock()
sys.modules["passlib"] = mock_passlib
sys.modules["passlib.context"] = mock_passlib.context
sys.modules["sentence_transformers"] = MagicMock()
sys.modules["presidio_analyzer"] = MagicMock()
sys.modules["presidio_anonymizer"] = MagicMock()
sys.modules["qdrant_client"] = MagicMock()
sys.modules["qdrant_client.http"] = MagicMock()
sys.modules["neo4j"] = MagicMock()
sys.modules["email_validator"] = MagicMock()

import importlib.metadata
orig_version = importlib.metadata.version
importlib.metadata.version = lambda pkg: "2.1.0" if pkg == "email-validator" else orig_version(pkg)

# Mock fastapi for environments missing it
def mock_decorator(*args, **kwargs):
    def decorator(func):
        return func
    return decorator

mock_router = MagicMock()
mock_router.post = mock_decorator
mock_router.get = mock_decorator
mock_router.put = mock_decorator
mock_router.delete = mock_decorator

class MockHTTPException(Exception):
    def __init__(self, status_code, detail=None, headers=None):
        self.status_code = status_code
        self.detail = detail
        self.headers = headers

mock_fastapi = MagicMock()
mock_fastapi.APIRouter = lambda *args, **kwargs: mock_router
mock_fastapi.Depends = lambda x=None: x
mock_fastapi.HTTPException = MockHTTPException
mock_fastapi.Header = MagicMock
mock_fastapi_responses = MagicMock()
mock_fastapi_responses.StreamingResponse = MagicMock()

sys.modules["fastapi"] = mock_fastapi
sys.modules["fastapi.responses"] = mock_fastapi_responses

mock_fastapi_security = MagicMock()
mock_fastapi_security.OAuth2PasswordBearer = MagicMock()
mock_fastapi_security.OAuth2PasswordRequestForm = MagicMock()
sys.modules["fastapi.security"] = mock_fastapi_security
print("[DEBUG] sys.modules mocks configured.")

import os
# Configure database URL before importing modules to ensure database initialization uses this SQLite database
db_path = "test_direct_query.db"
if os.path.exists(db_path):
    os.remove(db_path)
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path}"
os.environ["GROQ_API_KEY"] = ""

print("[DEBUG] Importing backend modules...")
from backend.core.database import Base, engine, async_session
from backend.api.query import query_knowledge_base, QueryRequest
from backend.models.user import User
from backend.models.workspace import Workspace
from backend.models.workspace_member import WorkspaceMember, WorkspaceRole
from backend.models.conversation import Conversation
from backend.models.query_log import QueryLog
from backend.models.reasoning_execution import ReasoningExecution
print("[DEBUG] Modules imported successfully.")

async def setup_database():
    print("[DEBUG] Creating database tables...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
    print("[DEBUG] Seeding database...")
    async with async_session() as session:
        # Create user
        user = User(id="user-123", email="test@example.com", hashed_password="mocked_password")
        session.add(user)
        # Create workspace
        workspace = Workspace(id="ws-123", name="Test Workspace", slug="test-workspace")
        session.add(workspace)
        await session.flush()
        
        # Add user to workspace
        member = WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role=WorkspaceRole.OWNER)
        session.add(member)
        
        # Create conversation
        conv = Conversation(id="conv-123", workspace_id=workspace.id, title="Test Session")
        session.add(conv)
        
        await session.commit()
    print("[DEBUG] Database set up completed.")

async def test_direct_query():
    await setup_database()
    
    print("\n── TEST 1: Conversational Query (Heuristics Fast Path) ──")
    from sqlalchemy import select
    async with async_session() as session:
        user = (await session.execute(select(User))).scalars().first()
        
        request = QueryRequest(
            question="hello",
            workspace_id="test-workspace",
            conversation_id="conv-123"
        )
        
        # Mock verify_workspace_access to return the workspace id
        import backend.api.query as query_module
        query_module.verify_workspace_access = AsyncMock(return_value="ws-123")
        
        response = await query_knowledge_base(
            request=None,
            query_req=request,
            db=session,
            current_user=user
        )
        
        print(f"   Answer: '{response.answer}'")
        print(f"   Query ID: {response.query_id}")
        assert "help you access your company's knowledge base" in response.answer
        print("   ✅ Conversational query verified.")

    print("\n── TEST 2: Deep Analysis Query (Fallback swarm execution) ──")
    async with async_session() as session:
        user = (await session.execute(select(User))).scalars().first()
        
        request = QueryRequest(
            question="What is the roadmap for superintelligence?",
            workspace_id="test-workspace",
            conversation_id="conv-123"
        )
        
        # This will route to DEEP_ANALYSIS, start durable execution, and log to DB
        response = await query_knowledge_base(
            request=None,
            query_req=request,
            db=session,
            current_user=user
        )
        
        print(f"   Answer: '{response.answer}'")
        print(f"   Query ID: {response.query_id}")
        
        # Verify ReasoningExecution table has a record
        stmt = select(ReasoningExecution)
        result = await session.execute(stmt)
        executions = result.scalars().all()
        print(f"   Reasoning Swarm Executions Created: {len(executions)}")
        assert len(executions) > 0
        print(f"   First Execution Status: '{executions[0].status}'")
        print("   ✅ Deep analysis query pipeline verified.")

if __name__ == "__main__":
    try:
        asyncio.run(test_direct_query())
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)
