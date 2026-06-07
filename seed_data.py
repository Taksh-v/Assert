
import asyncio
import uuid
from datetime import datetime
from sqlalchemy import select
from backend.core.database import async_session, init_db
from backend.models.workspace import Workspace
from backend.models.connector import Connector, ConnectorType, ConnectorStatus

async def seed():
    print("🌱 Seeding database...")
    await init_db()
    
    async with async_session() as session:
        # 1. Check if default workspace exists
        stmt = select(Workspace).where(Workspace.slug == "default-workspace")
        result = await session.execute(stmt)
        workspace = result.scalars().first()
        
        if not workspace:
            print("   Creating default workspace...")
            workspace = Workspace(
                id=str(uuid.uuid4()),
                name="Default Workspace",
                slug="default-workspace",
                settings={"theme": "dark"}
            )
            session.add(workspace)
            await session.flush()
        else:
            print("   Default workspace already exists.")

        # 2. Add some demo connectors
        connectors_to_add = [
            {
                "type": ConnectorType.NOTION,
                "config": {"mock": True, "workspace_name": "Demo Notion"},
                "status": ConnectorStatus.ACTIVE
            },
            {
                "type": ConnectorType.GOOGLE_DRIVE,
                "config": {"mock": True, "folder_id": "root"},
                "status": ConnectorStatus.ACTIVE
            },
            {
                "type": ConnectorType.SLACK,
                "config": {"mock": True, "channels": ["general"]},
                "status": ConnectorStatus.ACTIVE
            }
        ]

        for c_data in connectors_to_add:
            stmt = select(Connector).where(
                Connector.workspace_id == workspace.id,
                Connector.type == c_data["type"]
            )
            res = await session.execute(stmt)
            if not res.scalars().first():
                print(f"   Adding {c_data['type']} connector...")
                connector = Connector(
                    workspace_id=workspace.id,
                    type=c_data["type"],
                    config=c_data["config"],
                    status=c_data["status"],
                    last_synced_at=datetime.utcnow()
                )
                session.add(connector)
        
        await session.commit()
    print("✅ Seeding complete!")

if __name__ == "__main__":
    asyncio.run(seed())
