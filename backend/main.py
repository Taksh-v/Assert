"""
Assest — FastAPI Application Entry Point
Company knowledge base for Indian startups.
"""

from contextlib import asynccontextmanager
import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

from backend.core.config import get_settings
from backend.core.database import init_db, close_db
# from backend.events.redis_stream import event_stream
# from backend.workers.base_worker import worker_pool
# from backend.workers.fetch_worker import FetchWorkerFactory
# from backend.workers.parser_worker import ParserWorkerFactory
# from backend.workers.enrichment_worker import EnrichmentWorkerFactory
# from backend.workers.embedding_worker import EmbeddingWorkerFactory
# from backend.graph.memgraph_store import init_graph_store
# from backend.query.understanding import init_query_understander
# from backend.observability.telemetry import init_telemetry

# Import all models so tables are registered with SQLAlchemy
import backend.models  # noqa: F401

# Import routers
from backend.api.health import router as health_router
# from backend.api.webhooks import router as webhooks_router

settings = get_settings()


from backend.bot.slack import AssestSlackBot
from backend.workers.scheduler import BackgroundScheduler

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup and shutdown lifecycle events.
    """
    print("🧠 Assest Brain starting up...")
    
    # 1. Initialize DB
    await init_db()
    print("   ✅ Database tables created")
    
    # 2. Start Slack Bot in background only when explicitly enabled.
    slack_bot_task = None
    if settings.enable_slack_bot:
        try:
            bot = AssestSlackBot()
            slack_bot_task = asyncio.create_task(bot.start())
            print("   🚀 Slack Bot started in background")
        except Exception as e:
            print(f"   ⚠️  Slack Bot startup error: {e}")
    else:
        print("   ℹ️  Slack Bot disabled (set ENABLE_SLACK_BOT=true to enable)")
        
    # 3. Start Background Auto-Scheduler
    scheduler = BackgroundScheduler()
    scheduler.start()
    print("   🚀 Auto-Scheduler started (Memory reflection & DLQ retries)")

    yield

    # Shutdown
    print("\n🧠 Assest Brain shutting down...")
    if slack_bot_task:
        slack_bot_task.cancel()
        await asyncio.gather(slack_bot_task, return_exceptions=True)
    await scheduler.stop()
    await close_db()
    print("   ✅ Database closed")
    print("⛔ Assest Brain shut down.")


# ── App Instance ────────────────────────────────────────
app = FastAPI(
    title="Assest — Company Brain API",
    description=(
        "Knowledge base platform for Indian startups. "
        "Ingests from Notion, Google Drive, Slack, GitHub. "
        "Answers questions with grounded, cited responses."
    ),
    version=settings.app_version,
    lifespan=lifespan,
)

# ── CORS Middleware ─────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ─────────────────────────────────────────────
app.include_router(health_router)
# app.include_router(webhooks_router)

from backend.api.query import router as query_router
from backend.api.ingest import router as ingest_router
from backend.api.connectors import router as connectors_router
from backend.api.workspaces import router as workspaces_router
from backend.api.auth import router as auth_router
from backend.api.conversations import router as conversations_router
from backend.api.users import router as users_router
from backend.api.reasoning import router as reasoning_router
from backend.api.tools import router as tools_router

app.include_router(query_router, prefix="/api")
app.include_router(ingest_router, prefix="/api")
app.include_router(connectors_router, prefix="/api")
app.include_router(workspaces_router, prefix="/api")
app.include_router(auth_router, prefix="/api")
app.include_router(users_router, prefix="/api")
app.include_router(conversations_router)
app.include_router(reasoning_router, prefix="/api")
app.include_router(tools_router, prefix="/api")



@app.get("/")
async def root():
    """Root endpoint — redirects to API docs."""
    return {
        "app": "Assest",
        "tagline": "Your company's brain, always on.",
        "docs": "/docs",
        "health": "/health",
    }
