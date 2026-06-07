import asyncio
import os
import sys

# Ensure project root is in python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.core.database import init_db, close_db, async_session
from backend.models.document import Document
from sqlalchemy import select

async def main():
    await init_db()
    async with async_session() as session:
        stmt = select(Document)
        result = await session.execute(stmt)
        docs = result.scalars().all()
        
        print(f"📊 Total Ingested Documents in DB: {len(docs)}")
        print("──────────────────────────────────────────")
        for d in docs[:10]: # show first 10
            print(f"🔹 Title: {d.title}")
            print(f"  URL: {d.source_url}")
            print(f"  Connector ID: {d.connector_id}")
            print(f"  Ingested At: {d.last_ingested_at}")
            print(f"  Active: {d.is_active}")
            print("──────────────────────────────────────────")
            
    await close_db()

if __name__ == "__main__":
    asyncio.run(main())
