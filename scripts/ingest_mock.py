#!/usr/bin/env python3
import asyncio
from backend.core.database import init_db, async_session, upsert_idempotent
from backend.models.workspace import Workspace
from backend.models.connector import Connector, ConnectorType, ConnectorStatus
from backend.ingestion.pipeline import IngestionPipeline


async def main():
    await init_db()

    async with async_session() as session:
        workspace, _ = await upsert_idempotent(
            session,
            Workspace,
            lookup_fields={"slug": "default"},
            update_fields={"name": "Default Workspace"},
        )

        connector_lookup = {"workspace_id": workspace.id, "type": ConnectorType.NOTION}
        connector_update = {"config": {"mock": True}, "status": ConnectorStatus.ACTIVE}

        connector, _ = await upsert_idempotent(
            session,
            Connector,
            lookup_fields=connector_lookup,
            update_fields=connector_update,
        )

        await session.commit()

    print(f"Created workspace {workspace.id} and connector {connector.id}")

    pipeline = IngestionPipeline()
    await pipeline.run(connector.id)

    print("Ingestion pipeline finished")


if __name__ == "__main__":
    asyncio.run(main())
