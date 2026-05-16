
import asyncio
import os
from backend.core.config import get_settings
from backend.core.database import init_db, async_session
from sqlalchemy import select
from backend.models.workspace import Workspace
from backend.models.connector import Connector

async def verify():
    print("🔍 Verifying Connector Infrastructure...")
    settings = get_settings()
    
    # 1. Check .env
    print(f"   - Notion Client ID: {settings.notion_client_id[:8] if settings.notion_client_id else 'MISSING'}...")
    print(f"   - Slack Bot Token: {'SET' if settings.slack_bot_token else 'MISSING'}")
    
    # 2. Check Database
    await init_db()
    async with async_session() as session:
        stmt = select(Workspace).where(Workspace.slug == "default-workspace")
        result = await session.execute(stmt)
        workspace = result.scalars().first()
        if workspace:
            print(f"   - Workspace 'default-workspace' exists (ID: {workspace.id})")
            
            stmt = select(Connector).where(Connector.workspace_id == workspace.id)
            result = await session.execute(stmt)
            connectors = result.scalars().all()
            print(f"   - Found {len(connectors)} connector(s) in DB")
            for c in connectors:
                print(f"     * {c.type}: {c.status}")
        else:
            print("   - Default workspace not found in DB")

    print("\n✅ Infrastructure check complete.")

if __name__ == "__main__":
    asyncio.run(verify())
