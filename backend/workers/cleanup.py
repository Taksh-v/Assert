import logging
from datetime import datetime
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from backend.core.database import async_session
from backend.models.connector import Connector, ConnectorStatus
from backend.models.sync_run import SyncRun, SyncRunStatus
from backend.models.background_task import BackgroundTask
from backend.models.connector_sync_state import ConnectorSyncState
from backend.run_ledger.service import RunLedgerService

logger = logging.getLogger(__name__)

async def cleanup_zombie_runs() -> None:
    """
    Scans for active SyncRuns (queued, running) that are associated with completed,
    failed, cancelled, or missing BackgroundTasks, and transitions them to FAILED,
    releasing the connector locks so the scheduler doesn't skip them.
    """
    logger.info("🧹 Scanning database for zombie connector sync runs...")
    try:
        async with async_session() as session:
            stmt = select(SyncRun).where(SyncRun.status.in_(SyncRunStatus.ACTIVE))
            result = await session.execute(stmt)
            active_runs = result.scalars().all()
            
            if not active_runs:
                logger.info("🧹 No active sync runs found.")
                return

            cleaned_count = 0
            for run in active_runs:
                is_zombie = False
                reason = ""
                
                if not run.task_id:
                    is_zombie = True
                    reason = "No background task ID associated with sync run"
                else:
                    task_stmt = select(BackgroundTask).where(BackgroundTask.id == run.task_id)
                    task_res = await session.execute(task_stmt)
                    task = task_res.scalars().first()
                    
                    if not task:
                        is_zombie = True
                        reason = f"Associated background task {run.task_id} not found in database"
                    elif task.status in ["failed", "completed", "cancelled"]:
                        is_zombie = True
                        reason = f"Associated background task {run.task_id} is in terminal state '{task.status}'"
                
                if is_zombie:
                    logger.info(f"🧹 Cleaning up zombie SyncRun {run.id} for Connector {run.connector_id}. Reason: {reason}")
                    
                    # Update SyncRun to FAILED
                    await RunLedgerService.finish_run(
                        session,
                        SyncRun,
                        run.id,
                        SyncRunStatus.FAILED,
                        error=f"Task terminated prematurely: {reason}",
                    )
                    
                    # Mark connector in error state if it doesn't have other active runs
                    await session.execute(
                        update(Connector)
                        .where(Connector.id == run.connector_id)
                        .values(
                            status=ConnectorStatus.ERROR,
                            error_log={"last_error": f"Sync task aborted: {reason}", "timestamp": run.created_at.isoformat()},
                        )
                    )
                    
                    # Release lock in ConnectorSyncState
                    state_stmt = select(ConnectorSyncState).where(
                        ConnectorSyncState.connector_id == run.connector_id,
                        ConnectorSyncState.workspace_id == run.workspace_id,
                    )
                    state = (await session.execute(state_stmt)).scalars().first()
                    if state:
                        state.is_running = False
                        state.lock_owner = None
                        state.lock_acquired_at = None
                        state.lock_expires_at = None
                        state.last_error = f"Sync task aborted: {reason}"
                        logger.info(f"🧹 Released lock for connector {run.connector_id} in workspace {run.workspace_id}")
                    
                    cleaned_count += 1
            
            if cleaned_count > 0:
                await session.commit()
                logger.info(f"🧹 Successfully cleaned up {cleaned_count} zombie sync runs.")
            else:
                logger.info("🧹 No zombie sync runs identified.")
                
    except Exception as e:
        logger.error(f"🧹 Error during zombie sync runs cleanup: {e}", exc_info=True)
