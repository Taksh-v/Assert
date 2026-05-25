"""
ConnectorSyncRunner — Executes a single connector sync run attempt.
"""

import logging
import asyncio
from datetime import datetime, timedelta
from typing import Optional, List, Any, Dict

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import get_settings
from backend.core.database import async_session
from backend.models.connector import Connector, ConnectorStatus
from backend.models.connector_sync_state import ConnectorSyncState
from backend.models.sync_run import SyncRun, SyncRunStatus
from backend.core.security import decrypt_config
from backend.connectors.registry import connector_factory
from backend.observability.telemetry import Telemetry
from backend.ingestion.document_run import DocumentIngestionError
from backend.ingestion.runner import IngestionRunner
from backend.ingestion.document_store import SQLDocumentStore
from backend.ingestion.index_adapter import DefaultIndexAdapter
from backend.ingestion.pipeline_v2 import DefaultTemplate
from backend.run_ledger.service import RunLedgerService

from backend.ingestion.factory import IngestionPipelineFactory

logger = logging.getLogger(__name__)

class ConnectorSyncRunner:
    """
    Unified, deep execution runner for executing a single connector sync run.
    Owns connector lease use, fetching, document concurrency/fan-out, stats, DLQ routing.
    Delegates per-document work to IngestionRunner.
    """

    def __init__(self) -> None:
        self.settings = get_settings()
        self.runner = IngestionPipelineFactory.create_runner()

    def _matches_selected_id(self, raw_doc: Any, selected_ids: Optional[List[str]]) -> bool:
        """Safety filter for connectors that cannot pre-filter selected resources."""
        if not selected_ids:
            return True

        selected = {str(item) for item in selected_ids if item}
        source_id = str(getattr(raw_doc, "source_id", ""))
        metadata = getattr(raw_doc, "metadata", {}) or {}
        channel_id = str(metadata.get("channel_id", ""))

        candidates = {source_id}
        if channel_id:
            candidates.add(channel_id)
            candidates.add(f"slack-channel-{channel_id}")

        return bool(selected.intersection(candidates))

    async def run(self, sync_run_id: str) -> Dict[str, Any]:
        """
        Execute the sync run. Handles lease acquisition, fetching, concurrency, error containment,
        DLQ routing, and state persistence.
        """
        stats = {
            "connector_id": None,
            "processed": 0,
            "failed": 0,
            "fetched": 0,
            "skipped_selected": 0,
            "run_started_at": datetime.utcnow().isoformat(),
        }

        run_start_ts = datetime.utcnow()

        async with async_session() as session:
            # 1. Fetch SyncRun and Connector
            sync_run = (await session.execute(
                select(SyncRun).where(SyncRun.id == sync_run_id)
            )).scalars().first()
            if not sync_run:
                raise ValueError(f"SyncRun {sync_run_id} not found")

            if sync_run.status in SyncRunStatus.TERMINAL:
                return sync_run.stats or {}

            connector = (await session.execute(
                select(Connector).where(Connector.id == sync_run.connector_id)
            )).scalars().first()
            if not connector:
                raise ValueError(f"Connector {sync_run.connector_id} not found")

            stats["connector_id"] = connector.id
            connector_type = getattr(connector.type, "value", connector.type)
            workspace_id = connector.workspace_id

            # Telemetry: mark run start
            try:
                Telemetry.track_run_start(str(connector_type), sync_run.id)
            except Exception:
                logger.debug("Telemetry.track_run_start failed, ignoring")

            # 2. Acquire Lease Lock
            acquired = await self._acquire_connector_lock(
                session,
                connector_id=connector.id,
                workspace_id=workspace_id,
                lock_owner=sync_run.id,
            )
            if not acquired:
                await RunLedgerService.finish_run(
                    session,
                    SyncRun,
                    sync_run_id,
                    SyncRunStatus.FAILED,
                    error="Connector is already syncing",
                )
                await session.commit()
                return sync_run.stats or {}

            await RunLedgerService.finish_run(
                session,
                SyncRun,
                sync_run_id,
                SyncRunStatus.RUNNING,
            )
            await session.commit()


        # 3. Setup Connector Ingestion
        try:
            async with async_session() as session:
                sync_stmt = select(ConnectorSyncState).where(
                    ConnectorSyncState.connector_id == connector.id,
                    ConnectorSyncState.workspace_id == workspace_id,
                )
                sync_state = (await session.execute(sync_stmt)).scalars().first()
                since = None
                if sync_state and sync_state.last_sync_at:
                    since = sync_state.last_sync_at - timedelta(minutes=5)

                try:
                    config = decrypt_config(connector.config)
                except Exception as e:
                    logger.error(f"Failed to decrypt config for connector {connector.id}: {e}")
                    raise RuntimeError(f"Config decryption failed: {e}")

                try:
                    conn_impl = connector_factory.create(connector_type)
                except ValueError as e:
                    logger.error(f"Unsupported connector type: {connector_type} - {e}")
                    raise

            # 4. Fetch and Process Documents
            connection = await conn_impl.connect(config)
            semaphore = asyncio.Semaphore(5)  # Cap concurrency to 5 parallel documents
            tasks_list = []

            async def process_with_boundary(doc_obj):
                async with semaphore:
                    try:
                        # Prefer orchestrator seam if available
                        if getattr(self, "orchestrator", None) and hasattr(self.orchestrator, "process"):
                            await self.orchestrator.process(doc_obj, workspace_id, connector.id)
                        else:
                            await self.runner.process(doc_obj, workspace_id, connector.id)
                        return True
                    except Exception as doc_error:
                        stats["failed"] += 1
                        logger.warning(f"Error processing document {getattr(doc_obj, 'title', 'unknown')}: {doc_error}")
                        
                        try:
                            raw_content = getattr(doc_obj, "raw_content", getattr(doc_obj, "content", ""))
                            content_snippet = str(raw_content)[:2000] if raw_content else ""
                        except Exception:
                            content_snippet = "<UNREADABLE: error retrieving content>"
                            
                        raw_payload = {
                            "title": getattr(doc_obj, "title", "unknown"),
                            "source_id": getattr(doc_obj, "source_id", "unknown"),
                            "source_url": getattr(doc_obj, "source_url", "unknown"),
                            "source_type": getattr(doc_obj, "source_type", "unknown"),
                            "content": content_snippet
                        }
                        if isinstance(doc_error, DocumentIngestionError):
                            raw_payload.update(doc_error.failure_snapshot)
                            raw_payload["content"] = content_snippet
                        await Telemetry.log_failure(
                            workspace_id=workspace_id,
                            source_type=connector_type,
                            source_url=getattr(doc_obj, "source_url", "unknown"),
                            error=doc_error,
                            raw_payload=raw_payload
                        )
                        return False

            async for raw_doc in conn_impl.fetch_documents(
                connection,
                since=since,
                selected_ids=sync_run.selected_ids,
            ):
                if not self._matches_selected_id(raw_doc, sync_run.selected_ids):
                    stats["skipped_selected"] += 1
                    continue
                stats["fetched"] += 1
                tasks_list.append(asyncio.create_task(process_with_boundary(raw_doc)))

            if tasks_list:
                results = await asyncio.gather(*tasks_list)
                stats["processed"] = sum(1 for result in results if result)

            stats["run_completed_at"] = datetime.utcnow().isoformat()
            
            # 5. Transition SyncRun to Complete
            final_status = (
                SyncRunStatus.COMPLETED_WITH_ERRORS
                if int(stats.get("failed") or 0) > 0
                else SyncRunStatus.COMPLETED
            )
            await self._finish_sync_run(sync_run_id, final_status, stats=stats)
            # Telemetry: mark run finish
            try:
                run_duration = (datetime.utcnow() - run_start_ts).total_seconds()
                Telemetry.track_run_finish(str(connector_type), sync_run.id, run_duration, int(stats.get("processed") or 0), int(stats.get("failed") or 0))
            except Exception:
                logger.debug("Telemetry.track_run_finish failed, ignoring")
            return stats

        except Exception as e:
            logger.error(f"Sync failed for connector {connector.id}: {e}")
            stats["run_completed_at"] = datetime.utcnow().isoformat()
            await self._finish_sync_run(sync_run_id, SyncRunStatus.FAILED, stats=stats, error=str(e))
            try:
                run_duration = (datetime.utcnow() - run_start_ts).total_seconds()
                Telemetry.track_run_finish(str(connector_type), sync_run.id, run_duration, int(stats.get("processed") or 0), int(stats.get("failed") or 0))
            except Exception:
                logger.debug("Telemetry.track_run_finish failed, ignoring")
            raise e
        finally:
            # 6. Release Lease Lock
            async with async_session() as session:
                await self._release_connector_lock(
                    session,
                    connector_id=connector.id,
                    workspace_id=workspace_id,
                    lock_owner=sync_run_id,
                )
                await session.commit()

    async def _acquire_connector_lock(
        self,
        session: AsyncSession,
        connector_id: str,
        workspace_id: str,
        lock_owner: str,
    ) -> bool:
        now = datetime.utcnow()
        lease_minutes = max(70, getattr(self.settings, "auto_ingest_interval_minutes", 60) + 10)
        lease_expires_at = now + timedelta(minutes=lease_minutes)

        stmt = select(ConnectorSyncState).where(
            ConnectorSyncState.connector_id == connector_id,
            ConnectorSyncState.workspace_id == workspace_id,
        )
        state = (await session.execute(stmt)).scalars().first()

        if state and state.is_running and state.lock_owner != lock_owner:
            if state.lock_expires_at and state.lock_expires_at > now:
                return False

        if not state:
            state = ConnectorSyncState(
                connector_id=connector_id,
                workspace_id=workspace_id,
            )
            session.add(state)

        state.is_running = True
        state.lock_owner = lock_owner
        state.lock_acquired_at = now
        state.lock_expires_at = lease_expires_at
        state.updated_at = now
        await session.flush()
        return True

    async def _release_connector_lock(
        self,
        session: AsyncSession,
        connector_id: str,
        workspace_id: str,
        lock_owner: str,
    ) -> None:
        stmt = select(ConnectorSyncState).where(
            ConnectorSyncState.connector_id == connector_id,
            ConnectorSyncState.workspace_id == workspace_id,
        )
        state = (await session.execute(stmt)).scalars().first()
        if not state or state.lock_owner != lock_owner:
            return

        state.is_running = False
        state.lock_owner = None
        state.lock_acquired_at = None
        state.lock_expires_at = None
        state.updated_at = datetime.utcnow()

    async def _finish_sync_run(
        self,
        sync_run_id: str,
        status: str,
        stats: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> None:
        async with async_session() as session:
            sync_run = (await session.execute(
                select(SyncRun).where(SyncRun.id == sync_run_id)
            )).scalars().first()
            if not sync_run:
                raise ValueError(f"SyncRun {sync_run_id} not found")

            now = datetime.utcnow()
            
            # Use centralized RunLedgerService for lifecycle transitions
            await RunLedgerService.finish_run(
                session,
                SyncRun,
                sync_run_id,
                status,
                stats=stats,
                error=error,
            )

            # If failing, also mark the connector in error state
            if status == SyncRunStatus.FAILED:
                await session.execute(
                    update(Connector)
                    .where(Connector.id == sync_run.connector_id)
                    .values(
                        status=ConnectorStatus.ERROR,
                        error_log={"last_error": error, "timestamp": now.isoformat()},
                    )
                )

            # Persist SyncState metadata
            stmt = select(ConnectorSyncState).where(
                ConnectorSyncState.connector_id == sync_run.connector_id,
                ConnectorSyncState.workspace_id == sync_run.workspace_id,
            )
            state = (await session.execute(stmt)).scalars().first()
            if not state:
                state = ConnectorSyncState(
                    connector_id=sync_run.connector_id,
                    workspace_id=sync_run.workspace_id,
                )
                session.add(state)

            if error:
                state.last_error = error
            else:
                state.last_sync_at = now
                state.last_sync_token = None
                state.last_error = None
                await session.execute(
                    update(Connector)
                    .where(Connector.id == sync_run.connector_id)
                    .values(status=ConnectorStatus.ACTIVE, last_synced_at=now)
                )

            state.last_stats = stats or {}
            state.updated_at = now
            await session.commit()
