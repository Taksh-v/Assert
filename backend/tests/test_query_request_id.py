from types import SimpleNamespace

import pytest

from backend.api.query import QueryRequest, query_knowledge_base


@pytest.mark.asyncio
async def test_query_endpoint_forwards_request_id(monkeypatch):
    captured = {}

    async def fake_verify_workspace_access(workspace_id, db, current_user):
        return workspace_id

    class FakeQueryService:
        def __init__(self, db):
            self.db = db

        async def execute_query(self, **kwargs):
            captured.update(kwargs)
            return {
                "answer": "ok",
                "sources": [],
                "query_id": "query-123",
                "conversation_id": "conversation-123",
            }

    monkeypatch.setattr("backend.api.query.verify_workspace_access", fake_verify_workspace_access)
    monkeypatch.setattr("backend.api.query.QueryService", FakeQueryService)

    request = QueryRequest(question="What changed?", workspace_id="workspace-1")
    current_user = SimpleNamespace(id="user-1")

    response = await query_knowledge_base(
        request=None,
        query_req=request,
        db=SimpleNamespace(),
        current_user=current_user,
        x_request_id="request-abc",
    )

    assert captured["request_id"] == "request-abc"
    assert response.query_id == "query-123"
    assert response.conversation_id == "conversation-123"
