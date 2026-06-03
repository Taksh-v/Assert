import asyncio
import json
import sys
import pathlib
import pytest
from types import SimpleNamespace

# Ensure repo root is on PYTHONPATH when running tests
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.query.query_service import QueryService


class DummyOrchestrator:
    def __init__(self, delay: float = 2.0, answer: str = "hello from reasoning"):
        self.delay = delay
        self.answer = answer

    async def run_durable(self, *args, **kwargs):
        # simulate work
        await asyncio.sleep(self.delay)
        return {"answer": self.answer, "confidence": 0.9, "execution_id": "exec-123", "status": "completed", "iterations": 1}


@pytest.mark.asyncio
async def test_stream_query_emits_heartbeats_and_token(monkeypatch):
    # Arrange
    # Provide a fake DB session by passing None and using conversation_id to avoid DB writes
    svc = QueryService(db=None)

    # Patch ReasoningOrchestrator used by QueryService
    monkeypatch.setattr('backend.query.query_service.ReasoningOrchestrator', lambda: DummyOrchestrator(delay=1.0, answer="e2e-answer"))

    # Act
    events = []
    async for raw in svc.stream_query(question="hi", workspace_id="w1", user_id="u1", conversation_id="conv-1"):
        # parse SSE-like `data: {...}\n\n` chunks
        if not raw or not raw.startswith("data:"):
            continue
        payload = raw[len("data:"):].strip()
        try:
            obj = json.loads(payload)
        except Exception:
            continue
        events.append(obj)

    # Assert
    # must contain conversation, at least one status heartbeat containing 'Processing', token with the answer, and done
    types = [e.get('type') for e in events]
    assert 'conversation' in types
    assert 'status' in types
    assert any('Processing' in (e.get('status') or '') for e in events)
    assert any(e.get('type') == 'token' and e.get('token') == 'e2e-answer' for e in events)
    assert any(e.get('type') == 'done' for e in events)
    # ensure request_id propagated
    assert all('request_id' in e for e in events if isinstance(e, dict))
