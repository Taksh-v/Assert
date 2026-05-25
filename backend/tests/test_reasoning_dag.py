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
        await asyncio.sleep(0.1)
        return f"Mocked retrieve response for: {query}"

mock_module = MagicMock()
mock_module.RetrievalOrchestrator = MockRetrievalOrchestrator
sys.modules["backend.retrieval.orchestrator"] = mock_module

# Now import database and orchestrator safely without loading heavy ML modules
from backend.core.database import init_db, close_db, async_session
from backend.reasoning.orchestrator import ReasoningOrchestrator
from backend.models.reasoning_execution import ReasoningExecution
from sqlalchemy import select

async def test_dag_parallel_workflow(monkeypatch):
    print("🚀 Initializing test database for DAG verification...")
    await init_db()
    
    workspace_id = "test-workspace-dag"
    query = "Trigger parallel DAG tasks"
    
    # Custom plan mock response via the LLMClient mock
    from backend.generation.llm_client import LLMClient
    
    class MockResponse:
        def __init__(self, content):
            self.choices = [MagicMock()]
            self.choices[0].message = MagicMock()
            self.choices[0].message.content = content

    class MockCompletions:
        def create(self, messages, **kwargs):
            # Return a plan where Task 1 and Task 2 can run in parallel, and Task 3 depends on both
            plan_json = """{
                "goal": "Test Parallel Execution",
                "tasks": [
                    {"id": 1, "description": "Fetch documentation", "type": "retrieval", "dependencies": []},
                    {"id": 2, "description": "Fetch source code status", "type": "retrieval", "dependencies": []},
                    {"id": 3, "description": "Compile final comparative report", "type": "retrieval", "dependencies": [1, 2]}
                ],
                "initial_hypotheses": ["Parallel execution reduces overall iterations"]
            }"""
            
            user_content = messages[-1]["content"] if messages else ""
            if "json" in user_content.lower() or "plan" in user_content.lower():
                return MockResponse(plan_json)
            elif "analyst" in user_content.lower():
                return MockResponse("Analysis: Completed parallel research steps.")
            elif "synthesize" in user_content.lower():
                return MockResponse("# Parallel Execution Verification Complete")
            return MockResponse("Generic response")

    class MockChat:
        def __init__(self):
            self.completions = MockCompletions()

    # Temporarily monkey-patch the client.chat property to return our parallel mock
    monkeypatch.setenv("USE_NATIVE_ORCHESTRATION", "true")
    monkeypatch.setattr(LLMClient, "_client_init_failed", True, raising=False)
    monkeypatch.setattr(LLMClient, "chat", property(lambda self: MockChat()))
    
    orchestrator = ReasoningOrchestrator()
    
    print("🟢 Executing parallel durable reasoning...")
    result = await orchestrator.run_durable(
        query=query,
        workspace_id=workspace_id,
        user_id="test-user-id"
    )
    
    execution_id = result["execution_id"]
    print(f"   Execution ID: {execution_id}")
    print(f"   Status: {result['status']}")
    print(f"   Iterations: {result['iterations']}")
    
    # Verify iteration counts:
    # 1 (Planning) + 1 (Task 1 & Task 2 in parallel) + 1 (Task 3) = 3 iterations total
    assert result["iterations"] == 3, f"Expected 3 iterations due to parallel execution, but got {result['iterations']}"
    assert result["status"] == "completed"
    
    # Check Database Record
    async with async_session() as session:
        stmt = select(ReasoningExecution).where(ReasoningExecution.id == execution_id)
        res = await session.execute(stmt)
        execution = res.scalars().first()
        
        assert execution is not None
        assert execution.status == "completed"
        
        state_snap = execution.state_snapshot
        completed_ids = state_snap["completed_task_ids"]
        print(f"   Completed Task IDs: {completed_ids}")
        assert completed_ids == [1, 2, 3], f"Expected completed task IDs [1, 2, 3], got {completed_ids}"
        
    print("✅ Parallel execution verified in DB.")
    await close_db()
    print("🎉 DAG integration test completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_dag_parallel_workflow())
