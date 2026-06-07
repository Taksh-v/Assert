import os
import sys

# Ensure backend directory is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from backend.core.database import init_db, close_db, async_session
from backend.models.sync_run import SyncRun
from backend.run_ledger.service import RunLedgerService
from backend.models.run_ledger import RunStatus
from sqlalchemy import select


async def test_finish_run_transitions():
    await init_db()

    async with async_session() as session:
        # Create a SyncRun record
        sync_run = SyncRun(connector_id="test-conn", workspace_id="test-ws")
        session.add(sync_run)
        await session.flush()
        run_id = sync_run.id

        assert sync_run.canonical_status == RunStatus.QUEUED

        # Move run to RUNNING, then finish as COMPLETED (mimic real runner flow)
        await RunLedgerService.finish_run(session, SyncRun, run_id, RunStatus.RUNNING)
        await RunLedgerService.finish_run(session, SyncRun, run_id, RunStatus.COMPLETED, stats={"processed": 1})
        await session.commit()

    async with async_session() as session:
        res = (await session.execute(select(SyncRun).where(SyncRun.id == run_id))).scalars().first()
        assert res is not None
        assert res.canonical_status == RunStatus.COMPLETED
        assert res.completed_at is not None

    await close_db()
