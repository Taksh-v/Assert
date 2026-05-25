import pytest
from sqlalchemy import delete, select

from backend.core.database import init_db, async_session
from backend.core.security import encrypt_config
from backend.models.background_task import BackgroundTask
from backend.models.connector import Connector, ConnectorStatus, ConnectorType
from backend.models.connector_sync_state import ConnectorSyncState
from backend.models.sync_run import SyncRun, SyncRunStatus
from backend.workers.sync_coordinator import ConnectorSyncCoordinator
from backend.workers.task_queue import enqueue_task


@pytest.mark.asyncio
async def test_sync_run_is_product_state_and_task_is_execution_adapter():
    await init_db()
    workspace_id = "sync-run-workspace"

    async with async_session() as session:
        await session.execute(delete(BackgroundTask))
        await session.execute(delete(SyncRun))
        await session.execute(delete(ConnectorSyncState))
        await session.execute(delete(Connector).where(Connector.workspace_id == workspace_id))
        connector = Connector(
            workspace_id=workspace_id,
            type=ConnectorType.SLACK,
            config=encrypt_config({"access_token": "x"}),
            status=ConnectorStatus.ACTIVE,
        )
        session.add(connector)
        await session.flush()

        coordinator = ConnectorSyncCoordinator()
        sync_run, created = await coordinator.create_sync_run(
            session,
            connector,
            selected_ids=["C_SELECTED"],
            triggered_by="manual",
        )
        task_id = await enqueue_task("connector_sync", {"sync_run_id": sync_run.id}, db=session)
        await coordinator.attach_task(session, sync_run, task_id)
        await session.commit()

    assert created is True
    assert sync_run.status == SyncRunStatus.QUEUED
    assert sync_run.task_id == task_id

    async with async_session() as session:
        task = (await session.execute(select(BackgroundTask).where(BackgroundTask.id == task_id))).scalars().first()
        stored_run = (await session.execute(select(SyncRun).where(SyncRun.id == sync_run.id))).scalars().first()

    assert task.payload == {"sync_run_id": sync_run.id}
    assert task.status == "pending"
    assert stored_run.selected_ids == ["C_SELECTED"]


@pytest.mark.asyncio
async def test_active_sync_run_prevents_duplicate_connector_syncs():
    await init_db()
    workspace_id = "sync-run-dedup-workspace"

    async with async_session() as session:
        await session.execute(delete(SyncRun))
        await session.execute(delete(Connector).where(Connector.workspace_id == workspace_id))
        connector = Connector(
            workspace_id=workspace_id,
            type=ConnectorType.NOTION,
            config=encrypt_config({"access_token": "x"}),
            status=ConnectorStatus.ACTIVE,
        )
        session.add(connector)
        await session.flush()

        coordinator = ConnectorSyncCoordinator()
        first, first_created = await coordinator.create_sync_run(session, connector)
        second, second_created = await coordinator.create_sync_run(session, connector)
        await session.commit()

    assert first_created is True
    assert second_created is False
    assert second.id == first.id
