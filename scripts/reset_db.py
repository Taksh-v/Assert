import logging
import os
from backend.core.database import db_url
import backend.models
from backend.core.database import Base
from sqlalchemy import create_engine, text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def reset_db_sync():
    # Use synchronous engine for reset to avoid PgBouncer/asyncpg prepared statement issues
    sync_url = db_url.replace("postgresql+asyncpg://", "postgresql://")
    
    # Strip any extra args like statement_cache_size which are for asyncpg
    if "?" in sync_url:
        sync_url = sync_url.split("?")[0]
        
    engine = create_engine(sync_url)
    
    if "postgresql" in sync_url:
        with engine.connect() as conn:
            # Wrap in transaction
            with conn.begin():
                logger.info("🔥 Wiping PostgreSQL public schema...")
                conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
                conn.execute(text("CREATE SCHEMA public"))
                conn.execute(text("GRANT ALL ON SCHEMA public TO public"))
                logger.info("✨ Public schema recreated.")
    else:
        logger.info("🔥 Dropping all tables (SQLite)...")
        Base.metadata.drop_all(engine)

    logger.info("🛠️  Recreating all tables from metadata...")
    Base.metadata.create_all(engine)
    
    engine.dispose()
    logger.info("✅ Database reset complete.")

if __name__ == "__main__":
    reset_db_sync()
