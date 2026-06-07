from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.orchestrator import router as orch_router


def test_orchestrator_api_runs():
    app = FastAPI()
    app.include_router(orch_router, prefix="/api")
    client = TestClient(app)

    resp = client.post("/api/orchestrator/run", json={"intent": "summarize sales"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "results" in body
    # Should have both agent keys
    assert "agent_a" in body["results"] and "agent_b" in body["results"]
