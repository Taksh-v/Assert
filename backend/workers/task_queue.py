import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, Callable, Awaitable, Optional, List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.core.database import async_session
from backend.models.background_task import BackgroundTask

logger = logging.getLogger(__name__)

# Registry for task handlers
TASK_HANDLERS: Dict[str, Callable[[Dict[str, Any]], Awaitable[None]]] = {}

def register_task_handler(task_type: str):
    """Decorator to register a task handler."""
    def decorator(func: Callable[[Dict[str, Any]], Awaitable[None]]):
        TASK_HANDLERS[task_type] = func
        return func
    return decorator

async def enqueue_task(
    task_type: str, 
    payload: Dict[str, Any], 
    db: Optional[AsyncSession] = None
) -> str:
    """
    Enqueue a new background task.
    """
    new_task = BackgroundTask(
        task_type=task_type,
        payload=payload,
        status="pending"
    )
    
    if db:
        db.add(new_task)
        await db.flush()
        logger.info(f"Enqueued task {new_task.id} (type: {task_type}) in current session")
        return new_task.id
    else:
        async with async_session() as session:
            session.add(new_task)
            await session.commit()
            logger.info(f"Enqueued task {new_task.id} (type: {task_type}) in new session")
            return new_task.id

async def process_tasks(poll_interval: float = 5.0, max_retries: int = 3):
    """
    Continuous worker loop that polls for pending tasks and processes them concurrently.
    """
    logger.info("Starting concurrent background task worker loop...")
    
    # Cap concurrent task runs (e.g. max 3 parallel background syncs)
    semaphore = asyncio.Semaphore(3)
    
    while True:
        try:
            async with async_session() as session:
                # Find pending tasks
                stmt = select(BackgroundTask).where(
                    BackgroundTask.status == "pending"
                ).order_by(BackgroundTask.created_at.asc()).limit(5)
                
                result = await session.execute(stmt)
                tasks = result.scalars().all()
                
                if not tasks:
                    await asyncio.sleep(poll_interval)
                    continue

                # Mark all polled tasks as processing synchronously to claim them, and release locks
                for task in tasks:
                    task.status = "processing"
                    task.updated_at = datetime.utcnow()
                await session.commit()

                # Dispatch concurrent handler executions in the background
                for task in tasks:
                    asyncio.create_task(
                        _run_concurrent_task_handler(task.id, semaphore, max_retries)
                    )

        except Exception as e:
            logger.error(f"Error in task worker loop: {e}", exc_info=True)
            await asyncio.sleep(poll_interval)

async def _run_concurrent_task_handler(task_id: str, semaphore: asyncio.Semaphore, max_retries: int):
    """
    Executes a single task handler concurrently with lease lock, isolated session, and retry boundaries.
    """
    async with semaphore:
        task_type = None
        payload = None
        retry_count = 0
        
        try:
            async with async_session() as session:
                stmt = select(BackgroundTask).where(BackgroundTask.id == task_id)
                result = await session.execute(stmt)
                task = result.scalars().first()
                if not task:
                    return
                task_type = task.task_type
                payload = task.payload
                retry_count = task.retry_count
        except Exception as e:
            logger.error(f"Failed to fetch task {task_id} details in concurrent worker: {e}")
            return

        handler = TASK_HANDLERS.get(task_type)
        if not handler:
            logger.error(f"No handler registered for task type: {task_type}")
            try:
                async with async_session() as session:
                    stmt = select(BackgroundTask).where(BackgroundTask.id == task_id)
                    result = await session.execute(stmt)
                    task = result.scalars().first()
                    if task:
                        task.status = "failed"
                        task.error_log = {"error": f"No handler registered for {task_type}"}
                        task.updated_at = datetime.utcnow()
                        await session.commit()
            except Exception as e:
                logger.error(f"Failed to mark missing handler task {task_id} as failed: {e}")
            return

        # Execute handler outside of DB transaction to prevent lock hoarding
        success = True
        error_message = None
        try:
            logger.info(f"Processing task {task_id} (type: {task_type})")
            await handler(payload)
        except Exception as e:
            success = False
            error_message = e
            logger.error(f"Error processing task {task_id}: {e}", exc_info=True)

        # Update task execution result inside fresh session
        try:
            async with async_session() as session:
                stmt = select(BackgroundTask).where(BackgroundTask.id == task_id)
                result = await session.execute(stmt)
                task = result.scalars().first()
                if not task:
                    return

                if success:
                    task.status = "completed"
                    logger.info(f"Task {task.id} completed successfully")
                else:
                    task.retry_count = retry_count + 1
                    error_info = {
                        "error": str(error_message),
                        "timestamp": datetime.utcnow().isoformat(),
                        "attempt": task.retry_count
                    }
                    
                    current_log = dict(task.error_log or {})
                    if "errors" not in current_log:
                        current_log["errors"] = []
                    else:
                        current_log["errors"] = list(current_log["errors"])
                        
                    current_log["errors"].append(error_info)
                    task.error_log = current_log

                    if task.retry_count >= max_retries:
                        task.status = "failed"
                        logger.error(f"Task {task.id} failed after {task.retry_count} retries")
                    else:
                        task.status = "pending"  # Re-queue for retry
                        logger.info(f"Task {task.id} re-queued for retry (attempt {task.retry_count})")
                
                task.updated_at = datetime.utcnow()
                await session.commit()
        except Exception as e:
            logger.error(f"Failed to conclude task {task_id} status in DB: {e}")


async def _process_single_task(
    session: AsyncSession,
    task: BackgroundTask,
    max_retries: int = 3,
) -> None:
    """
    Process a single background task within an existing session.

    This is a thin helper used by tests to exercise the retry/failure
    logic without running the full concurrent polling loop.
    It executes the handler and updates `task` in-place; the caller is
    responsible for committing the session.
    """
    handler = TASK_HANDLERS.get(task.task_type)
    if not handler:
        task.status = "failed"
        task.error_log = {"error": f"No handler registered for {task.task_type}"}
        task.updated_at = datetime.utcnow()
        return

    success = True
    error_message = None
    try:
        await handler(task.payload)
    except Exception as e:
        success = False
        error_message = e

    if success:
        task.status = "completed"
        task.updated_at = datetime.utcnow()
    else:
        task.retry_count = (task.retry_count or 0) + 1
        error_info = {
            "error": str(error_message),
            "timestamp": datetime.utcnow().isoformat(),
            "attempt": task.retry_count,
        }
        current_log = dict(task.error_log or {})
        if "errors" not in current_log:
            current_log["errors"] = []
        else:
            current_log["errors"] = list(current_log["errors"])
        current_log["errors"].append(error_info)
        task.error_log = current_log

        if task.retry_count >= max_retries:
            task.status = "failed"
            logger.error(f"Task {task.id} failed after {task.retry_count} retries")
        else:
            task.status = "pending"
            logger.info(f"Task {task.id} re-queued for retry (attempt {task.retry_count})")

        task.updated_at = datetime.utcnow()

