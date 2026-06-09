"""
Setup Supabase — Initialize Schema and Storage.
"""

import asyncio
import logging
import sys
import os

# Add the project root to sys.path to allow absolute imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.core.config import get_settings
from backend.core.database import init_db
from backend.core.supabase import get_supabase_client

# Import all models to ensure they are registered with Base.metadata
from backend import models

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("setup_supabase")

async def initialize_schema():
    logger.info("Initializing Supabase Database Schema...")
    try:
        await init_db()
        logger.info("Database schema initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize database schema: {e}")
        raise

async def setup_storage():
    settings = get_settings()
    logger.info(f"Setting up Supabase Storage Bucket: {settings.supabase_storage_bucket}...")
    
    supabase = get_supabase_client()
    if not supabase:
        logger.error("Supabase client not configured. Check SUPABASE_URL and keys.")
        return

    try:
        # Check if bucket exists using list_buckets
        response = supabase.storage.list_buckets()
        bucket_names = [b.name for b in response]
        
        if settings.supabase_storage_bucket not in bucket_names:
            logger.info(f"Creating bucket: {settings.supabase_storage_bucket}")
            supabase.storage.create_bucket(settings.supabase_storage_bucket, options={"public": False})
            logger.info("Bucket created successfully.")
        else:
            logger.info(f"Bucket {settings.supabase_storage_bucket} already exists.")
    except Exception as e:
        logger.error(f"Failed to setup storage: {e}")

async def main():
    settings = get_settings()
    if "supabase.co" not in settings.database_url:
        logger.error("DATABASE_URL does not appear to be a Supabase URL in config.")
        logger.error(f"Current DATABASE_URL in config: {settings.database_url}")
        logger.info("Please ensure you have updated your .env file and restarted the environment.")
        return

    await initialize_schema()
    await setup_storage()
    logger.info("Supabase setup complete.")

if __name__ == "__main__":
    asyncio.run(main())
