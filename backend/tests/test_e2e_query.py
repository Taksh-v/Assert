"""
End-to-End Query Verification Test.

Uses FastAPI TestClient to hit real api routes (/api/query and /api/query/stream)
and verifies that we receive successful and properly formatted HTTP/SSE responses.
"""
import sys
import json
import asyncio
import pytest
from unittest.mock import MagicMock

# Mock heavy/external modules to prevent boot/network errors
mock_passlib = MagicMock()
mock_passlib.context = MagicMock()
mock_passlib.context.CryptContext = MagicMock()
sys.modules["passlib"] = mock_passlib
sys.modules["passlib.context"] = mock_passlib.context
sys.modules["sentence_transformers"] = MagicMock()
sys.modules["presidio_analyzer"] = MagicMock()
sys.modules["presidio_anonymizer"] = MagicMock()

import os
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_e2e.db"
os.environ.setdefault("GROQ_API_KEY", "")

import litellm
# Mock completions to avoid network/API calls in test
mock_response = MagicMock()
mock_response.choices = [
    MagicMock(
        message=MagicMock(content="Mocked answer for test_e2e_query")
    )
]
litellm.completion = MagicMock(return_value=mock_response)

# Mock acompletion for stream test and regular completions
async def mock_acompletion(*args, **kwargs):
    if kwargs.get("stream"):
        class AsyncGen:
            def __init__(self):
                self.done = False
            def __aiter__(self):
                return self
            async def __anext__(self):
                if self.done:
                    raise StopAsyncIteration
                self.done = True
                class MockChunk:
                    class Choice:
                        class Delta:
                            content = "Mocked token"
                        delta = Delta()
                    choices = [Choice()]
                return MockChunk()
        return AsyncGen()
    else:
        class MockResponse:
            class Choice:
                class Message:
                    content = '{"intent": "quick_lookup", "reasoning": "mocked", "scope": "specific", "temporal": "none"}'
                message = Message()
            choices = [Choice()]
        return MockResponse()


@pytest.fixture(autouse=True)
def patch_litellm_acompletion():
    """Scope litellm.acompletion mock to individual tests so it doesn't leak globally."""
    original = litellm.acompletion
    litellm.acompletion = mock_acompletion
    yield
    litellm.acompletion = original

from backend.core.vector_store import VectorStore
VectorStore.search = MagicMock(return_value=[])

async def mock_async_search(*args, **kwargs):
    return []

VectorStore.async_search = mock_async_search

from fastapi.testclient import TestClient
from backend.main import app
from backend.api.users import get_current_user
from backend.core.database import get_db, engine, Base
from backend.models.user import User
from backend.api.connectors import verify_workspace_access
from sqlalchemy.ext.asyncio import AsyncSession


# Mock Auth Dependency
class MockUser:
    id = "e2e-test-user-123"
    email = "test@example.com"
    hashed_password = "mocked-hash"
    is_active = True

async def mock_get_current_user():
    return MockUser()

async def mock_verify_workspace_access(*args, **kwargs):
    return "default-workspace-id"

# Setup overrides
app.dependency_overrides[get_current_user] = mock_get_current_user
sys.modules["backend.api.query"].verify_workspace_access = mock_verify_workspace_access
sys.modules["backend.api.connectors"].verify_workspace_access = mock_verify_workspace_access


async def init_test_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def test_query_endpoints():
    # Setup database synchronous helper
    asyncio.run(init_test_db())

    client = TestClient(app)

    print("── TEST 1: POST /api/query (Conversational Intent) ──")
    payload = {
        "question": "Hello there!",
        "workspace_id": "default-workspace",
        "response_format": "markdown",
        "reasoning_mode": False
    }
    
    response = client.post("/api/query", json=payload)
    print(f"   Status Code: {response.status_code}")
    print(f"   Response JSON: {response.json()}")
    
    assert response.status_code == 200
    data = response.json()
    assert "answer" in data
    assert "sources" in data
    assert len(data["answer"]) > 0
    print("   ✅ Conversational query response verified.\n")


    print("── TEST 2: POST /api/query (Quick Lookup Fallback Response) ──")
    payload_lookup = {
        "question": "What is the holiday policy?",
        "workspace_id": "default-workspace",
        "response_format": "markdown",
        "reasoning_mode": False
    }
    
    response_lookup = client.post("/api/query", json=payload_lookup)
    print(f"   Status Code: {response_lookup.status_code}")
    print(f"   Response JSON: {response_lookup.json()}")
    
    assert response_lookup.status_code == 200
    data_lookup = response_lookup.json()
    assert "answer" in data_lookup
    # Because LLM API key is empty/not configured, we expect a clean, offline fallback answer
    assert len(data_lookup["answer"]) > 0
    print("   ✅ Lookup query response verified.\n")


    print("── TEST 3: POST /api/query/stream (SSE Stream Verification) ──")
    payload_stream = {
        "question": "List latest team announcements",
        "workspace_id": "default-workspace",
        "response_format": "markdown",
        "reasoning_mode": False
    }
    
    # We use stream=True to read chunks
    with client.stream("POST", "/api/query/stream", json=payload_stream) as stream_resp:
        print(f"   Status Code: {stream_resp.status_code}")
        assert stream_resp.status_code == 200
        
        # Read the first few lines of the stream
        events = []
        for line in stream_resp.iter_lines():
            if line:
                decoded = line.decode("utf-8") if isinstance(line, bytes) else line
                print(f"   Stream chunk: {decoded}")
                events.append(decoded)
                if len(events) >= 5:
                    break
        
        assert len(events) > 0
        assert any("status" in ev or "token" in ev for ev in events)
        print("   ✅ SSE streaming query response verified.\n")

    # Cleanup E2E DB file
    try:
        os.remove("test_e2e.db")
    except:
        pass

    print("🎉 All E2E query routing and response tests passed successfully!")


if __name__ == "__main__":
    test_query_endpoints()
