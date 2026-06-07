"""
Assest — Background Worker Entry Point
Runs scheduled tasks, queues, and Slack Bot decoupled from the web API.
"""

import sys
import asyncio
import logging
from pathlib import Path

# Allow running from the backend directory by adding the repo root to `sys.path`.
if __package__ is None or __package__ == "":
    sys.path.append(str(Path(__file__).resolve().parents[1]))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("worker_main")

from backend.core.config import get_settings
from backend.core.database import init_db, close_db
from backend.bot.slack import AssestSlackBot
from backend.workers.scheduler import BackgroundScheduler

settings = get_settings()

async def main():
    logger.info("🧠 Assest Worker Process starting up...")
    
    # 1. Initialize DB
    await init_db()
    logger.info("✅ Database connected for worker process")

    # 1.1 Auto-create Qdrant vector collections
    try:
        from backend.core.vector_store import initialize_qdrant_collections
        initialize_qdrant_collections()
        logger.info("✅ Qdrant collections initialized for worker process")
    except Exception as e:
        logger.error(f"⚠️ Qdrant collection initialization failed: {e}")

    # 1.5 Clean up zombie sync runs from previous boots
    try:
        from backend.workers.cleanup import cleanup_zombie_runs
        await cleanup_zombie_runs()
    except Exception as e:
        logger.error(f"⚠️ Failed to run zombie sync cleanup: {e}")
    
    # 2. Start Slack Bot
    slack_bot_task = None
    if settings.enable_slack_bot:
        try:
            bot = AssestSlackBot()
            slack_bot_task = asyncio.create_task(bot.start())
            logger.info("🚀 Slack Bot started")
        except Exception as e:
            logger.error(f"⚠️ Slack Bot startup error: {e}")
    else:
        logger.info("ℹ️ Slack Bot disabled (set ENABLE_SLACK_BOT=true to enable)")
        
    # 3. Start Background Auto-Scheduler
    scheduler = BackgroundScheduler()
    scheduler.start()
    logger.info("🚀 Auto-Scheduler started (Memory reflection & DLQ retries)")

    try:
        # Keep the process alive indefinitely
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        pass
    except KeyboardInterrupt:
        pass
    finally:
        logger.info("🧠 Assest Worker Process shutting down...")
        if slack_bot_task:
            slack_bot_task.cancel()
            await asyncio.gather(slack_bot_task, return_exceptions=True)
        await scheduler.stop()
        await close_db()
        logger.info("✅ Database closed")
        logger.info("⛔ Assest Worker Process shut down.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Worker process interrupted by user.")
