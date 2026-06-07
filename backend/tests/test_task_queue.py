import asyncio
import pytest
from datetime import datetime
from sqlalchemy import select
from backend.core.database import init_db, close_db, async_session
from backend.models.background_task import BackgroundTask
from backend.workers.task_queue import enqueue_task, process_tasks, register_task_handler, TASK_HANDLERS

@pytest.mark.asyncio
async def test_task_queue_lifecycle():
    await init_db()
    
    # Clean up any existing tasks
    async with async_session() as session:
        from sqlalchemy import delete
        await session.execute(delete(BackgroundTask))
        await session.commit()

    # 1. Define a test handler
    task_processed = asyncio.Event()
    processed_payload = {}

    @register_task_handler("test_task")
    async def handle_test_task(payload):
        nonlocal processed_payload
        processed_payload = payload
        task_processed.set()

    # 2. Enqueue a task
    payload = {"hello": "world", "timestamp": datetime.utcnow().isoformat()}
    task_id = await enqueue_task("test_task", payload)
    
    assert task_id is not None
    
    # 3. Verify it's in the database
    async with async_session() as session:
        stmt = select(BackgroundTask).where(BackgroundTask.id == task_id)
        result = await session.execute(stmt)
        task = result.scalars().first()
        
        assert task is not None
        assert task.task_type == "test_task"
        assert task.status == "pending"
        assert task.payload == payload

    # 4. Start the worker loop in the background
    worker_task = asyncio.create_task(process_tasks(poll_interval=0.1))
    
    # 5. Wait for the task to be processed
    try:
        await asyncio.wait_for(task_processed.wait(), timeout=5.0)
        # Give it a moment to commit the status change
        await asyncio.sleep(0.5)
    except asyncio.TimeoutError:
        pytest.fail("Task processing timed out")
    finally:
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass

    # 6. Verify task status in database
    async with async_session() as session:
        stmt = select(BackgroundTask).where(BackgroundTask.id == task_id)
        result = await session.execute(stmt)
        task = result.scalars().first()
        
        assert task.status == "completed"
        assert processed_payload == payload

@pytest.mark.asyncio
async def test_task_failure_and_retry():
    await init_db()
    
    # Clean up
    async with async_session() as session:
        from sqlalchemy import delete
        await session.execute(delete(BackgroundTask))
        await session.commit()

    # 1. Define a failing handler
    attempts = 0
    @register_task_handler("failing_task")
    async def handle_failing_task(payload):
        nonlocal attempts
        attempts += 1
        raise ValueError(f"Planned failure {attempts}")

    # 2. Enqueue a task
    task_id = await enqueue_task("failing_task", {"foo": "bar"})
    
    # 3. Run the worker loop for a few cycles
    # We'll manually call _process_single_task to have better control or just run the loop
    from backend.workers.task_queue import _process_single_task
    
    async with async_session() as session:
        stmt = select(BackgroundTask).where(BackgroundTask.id == task_id)
        result = await session.execute(stmt)
        task = result.scalars().first()
        
        # First attempt
        await _process_single_task(session, task, max_retries=2)
        await session.commit()
        
    async with async_session() as session:
        stmt = select(BackgroundTask).where(BackgroundTask.id == task_id)
        result = await session.execute(stmt)
        task = result.scalars().first()
        assert task.status == "pending"
        assert task.retry_count == 1
        assert "Planned failure 1" in str(task.error_log)

        # Second attempt
        await _process_single_task(session, task, max_retries=2)
        await session.commit()

    async with async_session() as session:
        stmt = select(BackgroundTask).where(BackgroundTask.id == task_id)
        result = await session.execute(stmt)
        task = result.scalars().first()
        assert task.status == "failed"
        assert task.retry_count == 2
        assert "Planned failure 2" in str(task.error_log)

    await close_db()

if __name__ == "__main__":
    import sys
    import pytest
    sys.exit(pytest.main([__file__]))
