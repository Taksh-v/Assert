import asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient

import types


class DummySession:
    def __init__(self, storage: dict):
        self.storage = storage

    def add(self, obj):
        # simulate DB assigning id on add/commit
        obj.id = "dummy-exec-1"
        self.storage[obj.id] = obj

    async def commit(self):
        return None

    async def refresh(self, obj):
        return None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


def test_start_durable_monkeypatched(monkeypatch):
    # Monkeypatch async_session used by the durable endpoint
    storage = {}

    async def fake_async_session_cm():
        return DummySession(storage)

    # Patch the async_session name in the module
    import backend.api.orchestrator_durable as mod
    monkeypatch.setattr(mod, "async_session", lambda: DummySession(storage))

    app = FastAPI()
    app.include_router(mod.router, prefix="/api")
    client = TestClient(app)

    resp = client.post("/api/orchestrator/durable/start", json={"query": "what is sales", "workspace_id": "ws1"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "created"
    assert body["execution_id"] == "dummy-exec-1"
