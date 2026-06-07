import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy import event, text

async def test():
    engine = create_async_engine("sqlite+aiosqlite:///test_sprint3.db", connect_args={"check_same_thread": False, "timeout": 60})
    
    @event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()
        print("PRAGMA WAL and Synchronous set successfully!")

    async with engine.connect() as conn:
        res = await conn.execute(text("PRAGMA journal_mode"))
        mode = res.scalar()
        print(f"Current journal mode: {mode}")
        
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(test())
