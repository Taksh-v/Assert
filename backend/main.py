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
from backend.core.config import get_settings
from backend.core.database import init_db
from backend.api.health import router as health_router
from backend.api.webhooks import router as webhooks_router
from backend.api.query import router as query_router
from backend.api.connectors import router as connectors_router
from backend.api.workspaces import router as workspaces_router
from backend.api.auth import router as auth_router
from backend.api.identity_oauth import router as identity_oauth_router
from backend.api.users import router as users_router
from backend.api.conversations import router as conversations_router
from backend.api.reasoning import router as reasoning_router
from backend.api.observability import router as observability_router
from backend.api.llm import router as llm_router
from backend.api.orchestrator import router as orchestrator_router
from backend.api.orchestrator_durable import router as orchestrator_durable_router
from backend.api.memory import router as memory_router

settings = get_settings()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle events: startup and shutdown."""
    print("🧠 Assest Brain starting up...")
    await init_db()
    yield
    print("🛑 Assest Brain shutting down...")

app = FastAPI(
    title="Assest — Company Brain",
    description="High-precision agentic knowledge retrieval engine.",
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
app.include_router(health_router, tags=["Health"])
app.include_router(health_router, prefix="/api", tags=["Health"])
app.include_router(webhooks_router, prefix="/api")
app.include_router(query_router, prefix="/api")
app.include_router(connectors_router, prefix="/api")
app.include_router(workspaces_router, prefix="/api")
app.include_router(auth_router, prefix="/api")
app.include_router(identity_oauth_router, prefix="/api")
app.include_router(users_router, prefix="/api")
app.include_router(conversations_router, prefix="/api")
app.include_router(reasoning_router, prefix="/api")
app.include_router(observability_router, prefix="/api")
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
