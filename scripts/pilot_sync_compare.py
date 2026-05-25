"""Pilot harness to compare legacy ingestion pipeline vs new ConnectorSyncRunner.

Usage:
    PYTHONPATH=. python3 scripts/pilot_sync_compare.py <connector_id>

This script will:
- Create a SyncRun for the connector
- Run legacy `IngestionPipeline.run(connector_id)` and capture stats
- Run new `ConnectorSyncRunner.run(sync_run_id)` and capture stats
- Print a simple comparison report

Note: run this in a dev environment where connectors are mocked or safe to run.
"""
import asyncio
import os
import sys
from datetime import datetime

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.core.database import async_session
from backend.workers.sync_coordinator import ConnectorSyncCoordinator
from backend.ingestion.pipeline import IngestionPipeline
from backend.models.sync_run import SyncRun, SyncRunStatus

async def main(connector_id: str):
    # Create a SyncRun record directly for the connector (dev pilot)
    async with async_session() as session:
        sync_run = SyncRun(connector_id=connector_id, workspace_id="dev", triggered_by="pilot", status=SyncRunStatus.QUEUED)
        session.add(sync_run)
        await session.flush()
        run_id = sync_run.id

    print(f"Pilot compare started for connector {connector_id} at {datetime.utcnow().isoformat()}\n")

    print("Running legacy IngestionPipeline...")
    pipeline = IngestionPipeline()
    legacy_stats = await pipeline.run(connector_id)
    print(f"Legacy stats: {legacy_stats}\n")

    print("Running new ConnectorSyncRunner (via SyncRun)...")
    from backend.workers.sync_runner import ConnectorSyncRunner
    runner = ConnectorSyncRunner()
    new_stats = await runner.run(run_id)
    print(f"New runner stats: {new_stats}\n")

    print("Comparison complete.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/pilot_sync_compare.py <connector_id>")
        sys.exit(1)
    asyncio.run(main(sys.argv[1]))
