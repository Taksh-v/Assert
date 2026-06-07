import asyncio
from backend.core.database import init_db, async_session
from sqlalchemy import select
from backend.models.connector import Connector
from backend.core.security import decrypt_config

async def main():
    await init_db()
    async with async_session() as session:
        stmt = select(Connector)
        result = await session.execute(stmt)
        connectors = result.scalars().all()
        print(f"Total connectors found: {len(connectors)}")
        for idx, c in enumerate(connectors):
            print(f"\nConnector {idx+1}:")
            print(f"  ID: {c.id}")
            print(f"  Type: {c.type}")
            print(f"  Config (type {type(c.config)}): {repr(c.config)}")
            try:
                dec = decrypt_config(c.config) if isinstance(c.config, str) else c.config
                print(f"  Decrypted: {dec}")
            except Exception as e:
                print(f"  Decryption Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
