import logging
import asyncio
from sqlalchemy import text
from backend.core.database import engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def repair_schema():
    async with engine.begin() as conn:
        try:
            db_url = str(engine.url)
            
            # Check if column exists (Postgres style)
            if "postgresql" in db_url:
                result = await conn.execute(text(
                    "SELECT column_name FROM information_schema.columns WHERE table_name='users' AND column_name='supabase_id'"
                ))
                exists = result.fetchone() is not None
                
                if not exists:
                    logger.info("Adding supabase_id column to users table (Postgres)...")
                    await conn.execute(text("ALTER TABLE users ADD COLUMN supabase_id VARCHAR UNIQUE"))
                    await conn.execute(text("CREATE INDEX ix_users_supabase_id ON users (supabase_id)"))
                    logger.info("Successfully added supabase_id column.")
                else:
                    logger.info("supabase_id column already exists.")
            
            # SQLite style
            elif "sqlite" in db_url:
                # Use a slightly different approach for SQLite to avoid PRAGMA issues with text()
                result = await conn.execute(text("SELECT name FROM pragma_table_info('users')"))
                columns = [row[0] for row in result.fetchall()]
                
                if "supabase_id" not in columns:
                    logger.info("Adding supabase_id column to users table (SQLite)...")
                    await conn.execute(text("ALTER TABLE users ADD COLUMN supabase_id TEXT"))
                    await conn.execute(text("CREATE UNIQUE INDEX ix_users_supabase_id ON users (supabase_id)"))
                    logger.info("Successfully added supabase_id column.")
                else:
                    logger.info("supabase_id column already exists.")
                    
        except Exception as e:
            logger.error(f"Error repairing schema: {e}")
            logger.info("Attempting fallback: ALTER TABLE users ADD COLUMN supabase_id ...")
            try:
                # Fallback to direct alter
                if "postgresql" in db_url:
                    await conn.execute(text("ALTER TABLE users ADD COLUMN supabase_id VARCHAR UNIQUE"))
                else:
                    await conn.execute(text("ALTER TABLE users ADD COLUMN supabase_id TEXT"))
                logger.info("Fallback successful.")
            except Exception as e2:
                logger.error(f"Fallback failed: {e2}")
    
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(repair_schema())
