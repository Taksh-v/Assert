"""
Periodic Background Task Scheduler.

Automates:
1. Memory Reflection: Runs the ReflectorAgent periodically to maintain observations.
2. DLQ Retries: Scans and retries failed document ingestions from the Dead Letter Queue.
"""
import asyncio
import logging
from datetime import datetime, timedelta
from uuid import uuid4
from sqlalchemy import select, delete, update, or_

from backend.core.database import async_session
from backend.core.config import get_settings
from backend.models.connector import ConnectorStatus
from backend.memory.manager import MemoryManager
from backend.models.connector import Connector
from backend.models.connector_sync_state import ConnectorSyncState
from backend.models.failed_ingestion import FailedIngestion
from backend.ingestion.pipeline import IngestionPipeline

logger = logging.getLogger(__name__)

class BackgroundScheduler:
    """
    Lightweight async scheduler running in the background of the FastAPI lifecycle.
    """
    def __init__(self):
        self.memory_manager = MemoryManager()
        self._ingestion_pipeline = None
        self.settings = get_settings()
        self._tasks = []
        self._running = False

    def start(self):
        """Start all scheduled background tasks."""
        if self._running:
            return
        self._running = True
        logger.info("Starting background scheduler...")
        
        # Add tasks to event loop
        self._tasks.append(asyncio.create_task(self._memory_reflection_loop()))
        self._tasks.append(asyncio.create_task(self._dlq_retry_loop()))
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
                            
                            # Re-run pipeline for this connector
                            await self._get_ingestion_pipeline().run(
                                connector_id=connector.id,
                                selected_ids=selected_ids
                            )
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
        """Periodically iterate active connectors and trigger ingestion (default: every 60 minutes)."""
        # Small boot delay to avoid contention at startup
        await asyncio.sleep(120)

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
                    lock_owner = await self._acquire_connector_lock(connector)
                    if not lock_owner:
                        logger.info(f"Auto-Scheduler: Connector {connector.id} already ingesting; skipping.")
                        continue

                    # Kick off ingestion in background
                    task = asyncio.create_task(self._run_connector_ingest(connector, lock_owner))
                    self._tasks.append(task)

            except Exception as e:
                logger.error(f"Auto-Scheduler error in auto-ingest loop: {e}")

            # Sleep for configured interval
            await asyncio.sleep(interval * 60)

    def _coerce_retry_count(self, value) -> int:
        try:
            return int(value or 0)
        except Exception:
            return 0

    def _get_ingestion_pipeline(self) -> IngestionPipeline:
        """Lazily initialize the ingestion pipeline to keep app startup light."""
        if self._ingestion_pipeline is None:
            self._ingestion_pipeline = IngestionPipeline()
        return self._ingestion_pipeline

    async def _acquire_connector_lock(self, connector: Connector) -> str | None:
        """Acquire a lease in ConnectorSyncState so only one ingestion run works on a connector."""
        lease_owner = str(uuid4())
        now = datetime.utcnow()
        lease_expires_at = now + timedelta(minutes=max(70, getattr(self.settings, "auto_ingest_interval_minutes", 60) + 10))

        async with async_session() as session:
            stmt = select(ConnectorSyncState).where(
                ConnectorSyncState.connector_id == connector.id,
                ConnectorSyncState.workspace_id == connector.workspace_id,
            )
            result = await session.execute(stmt)
            state = result.scalars().first()

            if state and state.is_running and state.lock_expires_at and state.lock_expires_at > now:
                return None

            if not state:
                state = ConnectorSyncState(
                    connector_id=connector.id,
                    workspace_id=connector.workspace_id,
                    is_running=True,
                    lock_owner=lease_owner,
                    lock_acquired_at=now,
                    lock_expires_at=lease_expires_at,
                )
                session.add(state)
            else:
                state.is_running = True
                state.lock_owner = lease_owner
                state.lock_acquired_at = now
                state.lock_expires_at = lease_expires_at

            await session.commit()
            return lease_owner

    async def _release_connector_lock(self, connector: Connector, lock_owner: str, success: bool, error: str | None = None):
        """Release a previously acquired connector lease if we still own it."""
        async with async_session() as session:
            stmt = select(ConnectorSyncState).where(
                ConnectorSyncState.connector_id == connector.id,
                ConnectorSyncState.workspace_id == connector.workspace_id,
            )
            result = await session.execute(stmt)
            state = result.scalars().first()

            if not state or state.lock_owner != lock_owner:
                return

            state.is_running = False
            state.lock_owner = None
            state.lock_acquired_at = None
            state.lock_expires_at = None
            if error:
                state.last_error = error
            elif success:
                state.last_error = None
            await session.commit()

    async def _run_connector_ingest(self, connector: Connector, lock_owner: str):
        """Run ingestion for a single connector and update its status safely."""
        connector_id = connector.id
        logger.info(f"Auto-Scheduler: Running auto-ingest for connector {connector_id}")
        success = False
        error_message = None

        try:
            stats = await self._get_ingestion_pipeline().run(connector_id=connector_id, selected_ids=None)
            logger.info(f"Auto-Scheduler: Completed auto-ingest for connector {connector_id} with stats={stats}")
            success = True

        except Exception as e:
            error_message = str(e)
            logger.error(f"Auto-Scheduler: Auto-ingest failed for {connector_id}: {e}")
            async with async_session() as session:
                await session.execute(
                    update(Connector)
                    .where(Connector.id == connector_id)
                    .values(status="error", error_log={"last_error": str(e), "timestamp": datetime.utcnow().isoformat()})
                )
                await session.commit()

        finally:
            await self._release_connector_lock(connector, lock_owner, success=success, error=error_message)
