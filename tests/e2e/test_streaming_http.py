import json
import sys
import pathlib
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.main import app

# Monkeypatch imports
from backend.api.query import verify_workspace_access
from backend.api.users import get_current_user


class DummyOrchestrator:
    def __init__(self, delay: float = 1.0, answer: str = "http-answer"):
        self.delay = delay
        self.answer = answer

    async def run_durable(self, *args, **kwargs):
        import asyncio
        await asyncio.sleep(self.delay)
        return {"answer": self.answer, "confidence": 0.9, "execution_id": "exec-123", "status": "completed", "iterations": 1}


@pytest.fixture(autouse=True)
def _patch(monkeypatch):
    # Replace ReasoningOrchestrator used by QueryService
    monkeypatch.setattr('backend.query.query_service.ReasoningOrchestrator', lambda: DummyOrchestrator(delay=0.5, answer="http-answer"))
    # Avoid DB writes by stubbing conversation creation
    async def _fake_get_or_create(self, workspace_id, question, conversation_id=None):
        return conversation_id or "conv-test"
    monkeypatch.setattr('backend.query.query_service.QueryService._get_or_create_conversation', _fake_get_or_create)
    # Bypass workspace verification to return the requested workspace id (async)
    async def _fake_verify_workspace(workspace_id, db, current_user):
        return workspace_id
    monkeypatch.setattr('backend.api.query.verify_workspace_access', _fake_verify_workspace)
    # Override authentication to return a simple user via dependency override
    from backend.api.users import get_current_user
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id='u1')
    # Ensure get_db dependency returns None to avoid DB writes
    from backend.core.database import get_db
    app.dependency_overrides[get_db] = lambda: None
    yield
    app.dependency_overrides.clear()


def test_streaming_endpoint_sends_sse_messages():
    client = TestClient(app)
    payload = {"question": "hello", "workspace_id": "w1"}

    with client.stream("POST", "/api/query/stream", json=payload) as resp:
        assert resp.status_code == 200
        events = []
        for line in resp.iter_lines():
            if not line:
                continue
            text = line.decode('utf-8') if isinstance(line, bytes) else line
            if text.startswith('data:'):
                payload = text[len('data:'):].strip()
                try:
                    obj = json.loads(payload)
                    events.append(obj)
                except Exception:
                    continue

    types = [e.get('type') for e in events]
    assert 'conversation' in types
    assert any(e.get('type') == 'status' for e in events)
    assert any(e.get('type') == 'token' and e.get('token') == 'http-answer' for e in events)
    assert any(e.get('type') == 'done' for e in events)
    # request_id must be present on SSE messages
    assert all('request_id' in e for e in events if isinstance(e, dict))
