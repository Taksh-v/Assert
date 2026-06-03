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
    Continuous worker loop that polls for pending tasks and processes them.
    """
    logger.info("Starting background task worker loop...")
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

                for task in tasks:
                    await _process_single_task(session, task, max_retries)
                    await session.commit()

        except Exception as e:
            logger.error(f"Error in task worker loop: {e}", exc_info=True)
            await asyncio.sleep(poll_interval)

async def _process_single_task(session: AsyncSession, task: BackgroundTask, max_retries: int):
    """
    Process a single task with error handling and retries.
    """
    handler = TASK_HANDLERS.get(task.task_type)
    if not handler:
        logger.error(f"No handler registered for task type: {task.task_type}")
        task.status = "failed"
        task.error_log = {"error": f"No handler registered for {task.task_type}"}
        return

    task.status = "processing"
    task.updated_at = datetime.utcnow()
    # Commit immediately to release database locks before running potentially long-running handlers
    await session.commit()

    try:
        logger.info(f"Processing task {task.id} (type: {task.task_type})")
        await handler(task.payload)
        task.status = "completed"
        logger.info(f"Task {task.id} completed successfully")
    except Exception as e:
        logger.error(f"Error processing task {task.id}: {e}", exc_info=True)
        task.retry_count += 1
        error_info = {
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat(),
            "attempt": task.retry_count
        }
        
        if not task.error_log:
            task.error_log = {"errors": []}
        
        # Ensure we're working with a new dict to trigger SQLAlchemy's change tracking
        current_log = dict(task.error_log)
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
