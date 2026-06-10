"""
Periodic Background Task Scheduler.

Automates:
1. Memory Reflection: Runs the ReflectorAgent periodically to maintain observations.
2. DLQ Retries: Scans and retries failed document ingestions from the Dead Letter Queue.
"""
import asyncio
import logging
from datetime import datetime
from sqlalchemy import select

from backend.core.database import async_session
from backend.core.config import get_settings
from backend.models.connector import ConnectorStatus
from backend.models.connector import Connector
from backend.models.failed_ingestion import FailedIngestion
from backend.workers.task_queue import enqueue_task, process_tasks
from backend.workers.sync_coordinator import ConnectorSyncCoordinator
import backend.workers.handlers  # noqa: F401 - registers handlers
try:
    # Backwards-compatibility: some tests patch this symbol on the scheduler module.
    from backend.ingestion.pipeline import IngestionPipeline  # type: ignore
except Exception:
    IngestionPipeline = None

logger = logging.getLogger(__name__)

class BackgroundScheduler:
    """
    Lightweight async scheduler running in the background of the FastAPI lifecycle.
    """
    def __init__(self):
        from backend.memory.platform import get_platform_memory
        self.memory_manager = get_platform_memory()
        self.sync_coordinator = ConnectorSyncCoordinator()
        self.settings = get_settings()
        self._tasks = []
        self._running = False
        self._ingestion_pipeline = None

    def _get_ingestion_pipeline(self):
        """Lazily construct and return an `IngestionPipeline` instance.

        Tests may patch `backend.workers.scheduler.IngestionPipeline`, so prefer the
        module-level symbol when available to allow mock injection.
        """
        if self._ingestion_pipeline:
            return self._ingestion_pipeline

        try:
            if IngestionPipeline:
                self._ingestion_pipeline = IngestionPipeline()
                return self._ingestion_pipeline
        except Exception:
            pass

        try:
            from backend.ingestion.pipeline import IngestionPipeline as _IP
            self._ingestion_pipeline = _IP()
            return self._ingestion_pipeline
        except Exception:
            return None

    def start(self):
        """Start all scheduled background tasks."""
        self._running = True
        logger.info("Starting background scheduler...")
        
        # Add tasks to event loop
        self._tasks.append(asyncio.create_task(self._memory_reflection_loop()))
        self._tasks.append(asyncio.create_task(self._dlq_retry_loop()))
        self._tasks.append(asyncio.create_task(process_tasks()))
        # Auto-ingest loop (runs every hour by default)
        if getattr(self.settings, "enable_auto_ingest", True):
            self._tasks.append(asyncio.create_task(self._auto_ingest_loop()))

    async def stop(self):
        """Gracefully stop all tasks."""
        self._running = False
        logger.info("Stopping background scheduler...")
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []

    async def _memory_reflection_loop(self):
        """Periodically run Memory Reflector (every 12 hours)."""
        # Wait 1 minute after boot before first run to prevent boot slowdown
        await asyncio.sleep(60)
        
        while self._running:
            logger.info("Auto-Scheduler: Triggering Memory Reflection across all active workspaces...")
            try:
                async with async_session() as session:
                    # Find all workspaces with connectors
                    stmt = select(Connector.workspace_id).distinct()
                    result = await session.execute(stmt)
                    workspace_ids = result.scalars().all()
                
                for ws_id in workspace_ids:
                    logger.info(f"Auto-Scheduler: Reflecting memory for workspace {ws_id}")
                    summary = await self.memory_manager.trigger_reflection(workspace_id=ws_id)
                    logger.info(f"Auto-Scheduler: Workspace {ws_id} reflection completed. Summary: {summary}")
                    
            except Exception as e:
                logger.error(f"Auto-Scheduler error in memory reflection loop: {e}")
                
            # Run every 12 hours
            await asyncio.sleep(12 * 3600)

    async def _dlq_retry_loop(self):
        """Periodically scan and retry failed ingestions from the DLQ (every 30 minutes)."""
        # Wait 30 seconds after boot
        await asyncio.sleep(30)
        
        while self._running:
            logger.info("Auto-Scheduler: Scanning Dead Letter Queue (DLQ) for failed ingestions...")
            try:
                async with async_session() as session:
                    # Get failed ingestions still pending retry.
                    stmt = select(FailedIngestion).where(FailedIngestion.status == "pending")
                    result = await session.execute(stmt)
                    failed_records = result.scalars().all()
                    
                    if not failed_records:
                        logger.info("Auto-Scheduler: No failed ingestions in DLQ.")
                    
                    for record in failed_records:
                        retry_count = self._coerce_retry_count(record.retry_count)
                        if retry_count >= 3:
                            record.status = "failed"
                            await session.commit()
                            continue

                        logger.info(f"Auto-Scheduler: Retrying ingestion for {record.source_url} (Attempt {retry_count + 1})")
                        
                        # Find the connector for this failed ingestion dynamically
                        stmt_conn = select(Connector).where(Connector.workspace_id == record.workspace_id)
                        res_conn = await session.execute(stmt_conn)
                        connectors = res_conn.scalars().all()
                        connector = next((c for c in connectors if getattr(c.type, "value", c.type) == record.source_type), None)
                        
                        if not connector:
                            logger.error(f"Auto-Scheduler: No connector found for workspace {record.workspace_id} and source type {record.source_type}")
                            continue
                        
                        # Increment retry count first
                        record.retry_count = retry_count + 1
                        record.status = "retrying"
                        await session.commit()
                        
                        try:
                            # Extract source_id from raw_payload
                            source_id = None
                            if record.raw_payload and isinstance(record.raw_payload, dict):
                                source_id = record.raw_payload.get("source_id")
                            
                            selected_ids = [source_id] if (source_id and source_id != "unknown") else None
                            
                            async with async_session() as sync_session:
                                sync_run, _ = await self.sync_coordinator.create_sync_run(
                                    sync_session,
                                    connector,
                                    selected_ids=selected_ids,
                                    triggered_by="dlq_retry",
                                )
                                await sync_session.commit()

                            await self.sync_coordinator.execute_sync_run(sync_run.id)
                            logger.info(f"Auto-Scheduler: Successfully re-processed {record.source_url} from DLQ.")
                            # Delete from DLQ on success
                            await session.delete(record)
                            await session.commit()
                        except Exception as ingest_err:
                            logger.error(f"Auto-Scheduler: Retry failed for document {record.source_url}: {ingest_err}")
                            record.error_message = f"Retry Error: {ingest_err}"
                            record.status = "pending"
                            attempts = record.attempts or []
                            attempts.append({
                                "retry_count": record.retry_count,
                                "error": str(ingest_err),
                                "timestamp": datetime.utcnow().isoformat(),
                            })
                            record.attempts = attempts
                            await session.commit()
                            
            except Exception as e:
                logger.error(f"Auto-Scheduler error in DLQ retry loop: {e}")
                
            # Run every 30 minutes
            await asyncio.sleep(30 * 60)

    async def _auto_ingest_loop(self):
        """Periodically iterate active connectors and trigger ingestion (default: every 15 minutes)."""
        # Small boot delay to avoid contention at startup
        await asyncio.sleep(30)

        interval = getattr(self.settings, "auto_ingest_interval_minutes", 60)
        if not isinstance(interval, (int, float)):
            try:
                interval = int(interval)
            except Exception:
                interval = 60

        while self._running:
            logger.info("Auto-Scheduler: Starting auto-ingest pass for active connectors...")
            try:
                async with async_session() as session:
                    # Select connectors that are active
                    stmt = select(Connector).where(Connector.status == ConnectorStatus.ACTIVE)
                    result = await session.execute(stmt)
                    connectors = result.scalars().all()

                if not connectors:
                    logger.info("Auto-Scheduler: No active connectors to ingest.")

                for connector in connectors:
                    async with async_session() as session:
                        sync_run, created = await self.sync_coordinator.create_sync_run(
                            session,
                            connector,
                            selected_ids=None,
                            triggered_by="auto",
                        )
                        if not created:
                            logger.info(f"Auto-Scheduler: Connector {connector.id} already has sync run {sync_run.id}; skipping.")
                            await session.commit()
                            continue

                        task_id = await enqueue_task(
                            "connector_sync",
                            {"sync_run_id": sync_run.id},
                            db=session,
                        )
                        await self.sync_coordinator.attach_task(session, sync_run, task_id)
                        await session.commit()
                        logger.info(f"Auto-Scheduler: Enqueued sync run {sync_run.id} for connector {connector.id}")

            except Exception as e:
                logger.error(f"Auto-Scheduler error in auto-ingest loop: {e}")

            # Sleep for configured interval
            await asyncio.sleep(interval * 60)

    def _coerce_retry_count(self, value) -> int:
        try:
            return int(value or 0)
        except Exception:
            return 0
