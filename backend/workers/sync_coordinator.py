import logging
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import get_settings
from backend.core.database import async_session
from backend.models.connector import Connector, ConnectorStatus
from backend.models.connector_sync_state import ConnectorSyncState
from backend.models.sync_run import SyncRun, SyncRunStatus

logger = logging.getLogger(__name__)


class ConnectorSyncCoordinator:
    """
    Coordinates product-facing sync runs and connector leases.
    The queue executes work, but SyncRun is the stable status interface.
    """

    def __init__(self) -> None:
        self.settings = get_settings()

    async def create_sync_run(
        self,
        session: AsyncSession,
        connector: Connector,
        selected_ids: Optional[list[str]] = None,
        triggered_by: str = "manual",
    ) -> tuple[SyncRun, bool]:
        active = await self.get_active_sync_run(session, connector.id)
        if active:
            return active, False

        sync_run = SyncRun(
            connector_id=connector.id,
            workspace_id=connector.workspace_id,
            triggered_by=triggered_by,
            selected_ids=selected_ids,
            status=SyncRunStatus.QUEUED,
            stats={},
        )
        session.add(sync_run)
        await session.flush()
        return sync_run, True

    async def get_active_sync_run(self, session: AsyncSession, connector_id: str) -> Optional[SyncRun]:
        stmt = (
            select(SyncRun)
            .where(SyncRun.connector_id == connector_id, SyncRun.status.in_(SyncRunStatus.ACTIVE))
            .order_by(SyncRun.created_at.desc())
        )
        return (await session.execute(stmt)).scalars().first()

    async def get_latest_sync_run(self, session: AsyncSession, connector_id: str) -> Optional[SyncRun]:
        stmt = (
            select(SyncRun)
            .where(SyncRun.connector_id == connector_id)
            .order_by(SyncRun.created_at.desc())
        )
        return (await session.execute(stmt)).scalars().first()

    async def attach_task(self, session: AsyncSession, sync_run: SyncRun, task_id: str) -> None:
        sync_run.task_id = task_id
        sync_run.updated_at = datetime.utcnow()
        await session.flush()

    async def execute_sync_run(self, sync_run_id: str) -> dict[str, Any]:
        # Decide whether to run via the new ConnectorSyncRunner or the legacy IngestionPipeline
        async with async_session() as session:
            stmt = select(SyncRun).where(SyncRun.id == sync_run_id)
            sync_run = (await session.execute(stmt)).scalars().first()
            if not sync_run:
                raise ValueError(f"SyncRun {sync_run_id} not found")

            # Load connector to inspect type/id
            stmt = select(Connector).where(Connector.id == sync_run.connector_id)
            connector = (await session.execute(stmt)).scalars().first()
            if not connector:
                raise ValueError(f"Connector {sync_run.connector_id} not found")

        from backend.workers.sync_runner import ConnectorSyncRunner
        runner = ConnectorSyncRunner()
        return await runner.run(sync_run_id)

