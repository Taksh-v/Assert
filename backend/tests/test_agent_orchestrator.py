import pytest
from unittest.mock import AsyncMock, MagicMock
from backend.orchestrator.orchestrator import Orchestrator
from backend.models.reasoning_execution import ReasoningExecution

@pytest.mark.asyncio
async def test_orchestrator_invoice_flow(monkeypatch):
    # 1. Mock Database
    mock_db = AsyncMock()
    mock_execution = MagicMock(spec=ReasoningExecution)
    mock_execution.id = "test-exec-id"
    mock_execution.state_snapshot = {}
    
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = mock_execution
    mock_db.execute.return_value = mock_result
    
    # 2. Mock Planner LLM response
    invoice_plan = {
        "id": "test_invoice_wf",
        "steps": [
            {"id": 1, "skill": "customer_lookup", "inputs": {"customer_name": "Acme"}},
            {"id": 2, "skill": "invoice_lookup", "inputs": {"invoice_id": "INV-101"}}
        ]
    }
    
    async def mock_planner_run(self, intent, context):
        return invoice_plan

    monkeypatch.setattr("backend.orchestrator.planner.Planner.create_plan", mock_planner_run)

    # 3. Initialize Orchestrator
    orch = Orchestrator(mock_db)
    
    # 4. Run orchestrator
    result = await orch.run("Check my latest invoice", workspace_id="ws_1")
    
    # 5. Assertions
    assert result["status"] == "completed"
    assert "Invoice INV-101" in result["answer"]
    assert "Acme" in result["answer"]
    assert len(result["results"]) == 2

@pytest.mark.asyncio
async def test_orchestrator_pii_scrubbing(monkeypatch):
    mock_db = AsyncMock()
    mock_execution = MagicMock(spec=ReasoningExecution)
    mock_execution.id = "pii-exec-id"
    mock_execution.state_snapshot = {}
    
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = mock_execution
    mock_db.execute.return_value = mock_result
    
    # Plan that returns PII in output
    pii_plan = {
        "id": "pii_wf",
        "steps": [
            {"id": 1, "skill": "customer_lookup", "inputs": {"customer_name": "John Doe"}}
        ]
    }
    
    async def mock_planner_run(self, intent, context):
        return pii_plan
    
    async def mock_dispatch(self, step, context):
        return {"name": "John Doe", "email": "john.doe@example.com"}

    monkeypatch.setattr("backend.orchestrator.planner.Planner.create_plan", mock_planner_run)
    monkeypatch.setattr("backend.orchestrator.dispatcher.Dispatcher.dispatch", mock_dispatch)

    orch = Orchestrator(mock_db)
    result = await orch.run("Who is the customer?", workspace_id="ws_1")
    
    assert result["status"] == "completed"
    # Email should be scrubbed
    assert "john.doe@example.com" not in result["answer"]
    assert "<EMAIL>" in result["answer"]
