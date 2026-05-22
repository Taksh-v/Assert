"""
Integration Test for Sprint 4 Automation Features.

Tests that the BackgroundScheduler correctly initializes, schedules,
triggers tasks, and stops cleanly.
"""
import sys
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
import pytest

# Mock external dependencies for offline testing
mock_passlib = MagicMock()
mock_passlib.context = MagicMock()
mock_passlib.context.CryptContext = MagicMock()
sys.modules["passlib"] = mock_passlib
sys.modules["passlib.context"] = mock_passlib.context
sys.modules["groq"] = MagicMock()
sys.modules["sentence_transformers"] = MagicMock()
sys.modules["presidio_analyzer"] = MagicMock()
sys.modules["presidio_anonymizer"] = MagicMock()

import os
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test_sprint4.db")

from backend.workers.scheduler import BackgroundScheduler

@pytest.mark.asyncio
async def test_scheduler_lifecycle():
    print("── TEST 1: BackgroundScheduler Initialization and Start ──")
    scheduler = BackgroundScheduler()
    
    # Mock loop methods to prevent long sleeps and actually check if they trigger logic
    scheduler._memory_reflection_loop = AsyncMock()
    scheduler._dlq_retry_loop = AsyncMock()
    scheduler._auto_ingest_loop = AsyncMock()
    
    scheduler.start()
    print("   BackgroundScheduler started.")
    
    # Verify tasks are added
    assert len(scheduler._tasks) == 3
    assert scheduler._running is True
    print("   ✅ Scheduler start and tasks creation verified.")

    print("── TEST 2: BackgroundScheduler Stopping and Cleanup ──")
    await scheduler.stop()
    print("   BackgroundScheduler stopped.")
    
    assert scheduler._running is False
    assert len(scheduler._tasks) == 0
    print("   ✅ Scheduler stop and tasks cleanup verified.")


@patch("backend.workers.scheduler.IngestionPipeline")
@pytest.mark.asyncio
async def test_scheduler_lazy_pipeline_initialization(mock_pipeline_class):
    print("── TEST 2b: Scheduler Lazy Ingestion Pipeline ──")
    scheduler = BackgroundScheduler()

    mock_pipeline_class.assert_not_called()
    pipeline = scheduler._get_ingestion_pipeline()

    mock_pipeline_class.assert_called_once()
    assert pipeline is mock_pipeline_class.return_value
    print("   ✅ Scheduler does not initialize ingestion pipeline during startup.")


@patch("backend.workers.scheduler.async_session")
@pytest.mark.asyncio
async def test_scheduler_reflection_execution(mock_async_session):
    print("── TEST 3: Memory Reflection Loop Execution ──")
    scheduler = BackgroundScheduler()
    
    # Mock MemoryManager trigger_reflection
    scheduler.memory_manager.trigger_reflection = AsyncMock(return_value="Reflection completed successfully")
    
    # Mock DB query to return one workspace
    mock_session_inst = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = ["workspace-test-123"]
    mock_session_inst.execute.return_value = mock_result
    mock_async_session.return_value.__aenter__.return_value = mock_session_inst
    
    # Run the loop pass once by setting running to False during execution
    scheduler._running = True
    
    # Patch asyncio.sleep to shut down the loop on the second call (inside the while loop)
    sleep_calls = 0
    async def mock_sleep(seconds):
        nonlocal sleep_calls
        sleep_calls += 1
        if sleep_calls >= 2:
            scheduler._running = False
        
    with patch("asyncio.sleep", mock_sleep):
        await scheduler._memory_reflection_loop()
    
    # Assertions
    scheduler.memory_manager.trigger_reflection.assert_called_once_with(workspace_id="workspace-test-123")
    print("   ✅ Memory Reflection execution trigger verified.")
    print("🎉 All Sprint 4 Automation integration tests passed!")


async def main():
    await test_scheduler_lifecycle()
    await test_scheduler_reflection_execution()


if __name__ == "__main__":
    asyncio.run(main())
