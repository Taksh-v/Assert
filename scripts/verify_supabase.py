"""
Verify Supabase Connection and Health.
"""
import asyncio
import logging
import sys
import os
from sqlalchemy import text

# Add the project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.core.config import get_settings
from backend.core.database import engine, async_session
from backend.core.supabase import get_supabase_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("verify_supabase")

async def check_db():
    logger.info("Testing Database Connection...")
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT 1"))
            val = result.scalar()
            if val == 1:
                logger.info("✅ Database Connection: SUCCESS")
                
                # Check tables
                res = await conn.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"))
                tables = [row[0] for row in res.fetchall()]
                logger.info(f"📊 Tables found: {', '.join(tables)}")
                return True
    except Exception as e:
        logger.error(f"❌ Database Connection: FAILED - {e}")
        return False

async def check_storage():
    logger.info("Testing Storage Connection...")
    settings = get_settings()
    supabase = get_supabase_client()
    if not supabase:
        logger.error("❌ Supabase client: NOT CONFIGURED")
        return False
    
    try:
        buckets = supabase.storage.list_buckets()
        bucket_names = [b.name for b in buckets]
        if settings.supabase_storage_bucket in bucket_names:
            logger.info(f"✅ Storage Bucket '{settings.supabase_storage_bucket}': FOUND")
            return True
        else:
            logger.warn(f"⚠️ Storage Bucket '{settings.supabase_storage_bucket}': NOT FOUND")
            return False
    except Exception as e:
        logger.error(f"❌ Storage Connection: FAILED - {e}")
        return False

async def main():
    db_ok = await check_db()
    storage_ok = await check_storage()
    
    if db_ok and storage_ok:
        logger.info("\n🚀 SYSTEM HEALTH: OPTIMAL (All Supabase services connected)")
    else:
        logger.error("\n🔴 SYSTEM HEALTH: DEGRADED (Check errors above)")

if __name__ == "__main__":
    asyncio.run(main())
