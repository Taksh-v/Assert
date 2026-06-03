"""
Assest — FastAPI Application Entry Point
Company knowledge base for Indian startups.
"""

import sys
from contextlib import asynccontextmanager
from pathlib import Path
import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging


# Allow `python3 main.py` from the backend directory by adding the repo root to `sys.path`.
if __package__ is None or __package__ == "":
    sys.path.append(str(Path(__file__).resolve().parents[1]))

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
from backend.core.llm_impl import validate_models_on_startup
from backend.core.metrics import LLM_CALLS_TOTAL, LLM_CALL_DURATION_SECONDS
from backend.core.config import get_settings

try:
    from prometheus_client import start_http_server
except Exception:
    start_http_server = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup and shutdown lifecycle events.
    """
    print("🧠 Assest Brain starting up...")
    
    # 1. Initialize DB
    await init_db()
    print("   ✅ Database tables created")

    # 1.1 Auto-create Qdrant vector collections
    try:
        from backend.core.vector_store import initialize_qdrant_collections
        initialize_qdrant_collections()
        print("   ✅ Qdrant collections initialized")
    except Exception as e:
        print(f"   ⚠️  Qdrant collection initialization failed: {e}")

    # 1.6 Start Prometheus metrics endpoint if enabled
    if settings.enable_prometheus and start_http_server:
        prom_port = settings.prometheus_port
        try:
            start_http_server(prom_port)
            print(f"   ✅ Prometheus metrics endpoint started on :{prom_port}")
        except Exception as e:
            print(f"   ⚠️  Failed to start Prometheus metrics endpoint: {e}")

    # 1.5 Validate LLM model configuration (warnings only)
    try:
        warnings = await validate_models_on_startup()
        if warnings:
            for w in warnings:
                print(f"   ⚠️  LLM config warning: {w}")
            # If strict validation is enabled, fail fast to surface config issues
            if settings.strict_model_validation:
                print("   ❌ Strict model validation enabled — aborting startup due to LLM config warnings")
                sys.exit(1)
    except Exception:
        print("   ⚠️  LLM startup validation failed (see logs)")
    
    yield

    # Shutdown
    print("\n🧠 Assest Brain shutting down...")
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

# ── Rate Limiting ──────────────────────────────────────
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── Routers ─────────────────────────────────────────────
app.include_router(health_router)
app.include_router(health_router, prefix="/api")
# app.include_router(webhooks_router)

from backend.api.query import router as query_router
from backend.api.connectors import router as connectors_router
from backend.api.workspaces import router as workspaces_router
from backend.api.auth import router as auth_router
from backend.api.conversations import router as conversations_router
from backend.api.users import router as users_router
from backend.api.reasoning import router as reasoning_router
from backend.api.llm import router as llm_router
from backend.api.orchestrator import router as orchestrator_router
from backend.api.orchestrator_durable import router as orchestrator_durable_router
from backend.api.memory import router as memory_router

app.include_router(query_router, prefix="/api")
app.include_router(connectors_router, prefix="/api")
app.include_router(workspaces_router, prefix="/api")
app.include_router(auth_router, prefix="/api")
app.include_router(users_router, prefix="/api")
app.include_router(conversations_router)
app.include_router(reasoning_router, prefix="/api")
app.include_router(llm_router, prefix="/api")
app.include_router(orchestrator_router, prefix="/api")
app.include_router(orchestrator_durable_router, prefix="/api")
app.include_router(memory_router, prefix="/api")



@app.get("/")
async def root():
    """Root endpoint — redirects to API docs."""
    return {
        "app": "Assest",
        "tagline": "Your company's brain, always on.",
        "docs": "/docs",
        "health": "/health",
    }
