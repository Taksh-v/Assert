import asyncio
import os
import sys
from unittest.mock import MagicMock

# Ensure backend directory is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

# Mock the entire backend.retrieval.orchestrator module before any imports
class MockRetrievalOrchestrator:
    def __init__(self, *args, **kwargs):
        pass

    async def retrieve_reasoning_context(self, query: str, workspace_id: str, user_id=None) -> str:
        return "Mocked reasoning context retrieval from Phase 2."

mock_module = MagicMock()
mock_module.RetrievalOrchestrator = MockRetrievalOrchestrator
sys.modules["backend.retrieval.orchestrator"] = mock_module

# Now import database and orchestrator safely without loading heavy ML modules
from backend.core.database import init_db, close_db, async_session
from backend.reasoning.orchestrator import ReasoningOrchestrator
from backend.models.reasoning_execution import ReasoningExecution
from sqlalchemy import select

async def test_durable_workflow_lifecycle():
    print("🚀 Initializing test database...")
    await init_db()
    
    workspace_id = "test-workspace-id"
    query = "Run a durable query that requires human approval to proceed"
    
    orchestrator = ReasoningOrchestrator()
    
    # 1. Start the durable run
    print("🟢 Starting durable reasoning execution...")
    result = await orchestrator.run_durable(
        query=query,
        workspace_id=workspace_id,
        user_id="test-user-id"
    )
    
    execution_id = result["execution_id"]
    print(f"   Created Execution ID: {execution_id}")
    print(f"   Initial Status: {result['status']}")
    print(f"   Awaiting Approval: {result['awaiting_approval']}")
    
    assert result["status"] == "suspended", f"Expected 'suspended' but got {result['status']}"
    assert result["awaiting_approval"] is True, "Expected awaiting_approval to be True"
    assert result["iterations"] == 2, f"Expected 2 iterations, got {result['iterations']}"

    
    # 2. Check Database Checkpoint
    print("🔍 Verifying state snapshot is saved in DB...")
    async with async_session() as session:
        stmt = select(ReasoningExecution).where(ReasoningExecution.id == execution_id)
        res = await session.execute(stmt)
        execution = res.scalars().first()
        
        assert execution is not None, "Execution record not found in database!"
        assert execution.status == "suspended", f"Expected DB status 'suspended' but got {execution.status}"
        assert execution.current_task_index == 1, f"Expected task index 1, got {execution.current_task_index}"
        
        state_snap = execution.state_snapshot
        assert state_snap["query"] == query
        assert state_snap["awaiting_approval"] is True
        print("   ✅ DB Checkpoint verified successfully.")

    # 3. Resume the execution
    print("🟢 Resuming execution with human approval input...")
    resume_result = await orchestrator.run_durable(
        query=query,
        workspace_id=workspace_id,
        execution_id=execution_id,
        user_input="Approval granted. Please compile the final analysis report.",
        user_id="test-user-id"
    )
    
    print(f"   Resumed Status: {resume_result['status']}")
    print(f"   Final Answer Generated: {resume_result['answer'] is not None}")
    
    assert resume_result["status"] == "completed", f"Expected 'completed' but got {resume_result['status']}"
    assert resume_result["awaiting_approval"] is False, "Expected awaiting_approval to be False"
    assert resume_result["answer"] is not None, "Expected final answer to be populated"
    
    # 4. Check DB after completion
    print("🔍 Verifying DB status is updated to completed...")
    async with async_session() as session:
        stmt = select(ReasoningExecution).where(ReasoningExecution.id == execution_id)
        res = await session.execute(stmt)
        execution = res.scalars().first()
        assert execution.status == "completed"
        print("   ✅ DB Final status verified.")

    # 5. Verify Tracing (OpenTelemetry logs/telemetry.log)
    print("🔍 Verifying telemetry trace logs...")
    log_file = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../logs/telemetry.log"))
    assert os.path.exists(log_file), f"Telemetry log file not found at {log_file}"

    
    with open(log_file, "r") as f:
        log_content = f.read()
        
    assert "planner_agent" in log_content, "Expected planner_agent span in trace log"
    assert "researcher_agent" in log_content, "Expected researcher_agent span in trace log"
    assert "analyst_agent" in log_content, "Expected analyst_agent span in trace log"
    assert "synthesizer_agent" in log_content, "Expected synthesizer_agent span in trace log"
    print("   ✅ Telemetry spans successfully logged in logs/telemetry.log.")
    
    await close_db()
    print("🎉 All integration tests passed successfully!")

if __name__ == "__main__":
    asyncio.run(test_durable_workflow_lifecycle())
