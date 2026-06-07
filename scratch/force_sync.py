
import asyncio
import sys
from backend.core.database import async_session
from backend.models.connector import Connector
from sqlalchemy import select, update

async def force_full_sync(connector_type):
    async with async_session() as session:
        stmt = select(Connector).where(Connector.type == connector_type)
        result = await session.execute(stmt)
        connector = result.scalars().first()
        
        if connector:
            print(f"🔄 Resetting sync timestamp for {connector_type}...")
            connector.last_synced_at = None
            await session.commit()
            print("✅ Done. Next sync will be a FULL sync.")
        else:
            print(f"❌ No connector found for type: {connector_type}")

if __name__ == "__main__":
    c_type = sys.argv[1] if len(sys.argv) > 1 else "notion"
    asyncio.run(force_full_sync(c_type))
