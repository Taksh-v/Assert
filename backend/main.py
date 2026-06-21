"""
Assest — FastAPI Application Entry Point
Company knowledge base for Indian startups.
"""

import sys
from pathlib import Path
import asyncio
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from backend.core.config import get_settings
from backend.core.lifecycle import app_lifespan
from backend.api.health import router as health_router
from backend.api.webhooks import router as webhooks_router
from backend.api.query import router as query_router
from backend.api.connectors import router as connectors_router
from backend.api.workspaces import router as workspaces_router
from backend.api.documents import router as documents_router
from backend.api.auth import router as auth_router
from backend.api.users import router as users_router
from backend.api.conversations import router as conversations_router
from backend.api.reasoning import router as reasoning_router
from backend.api.observability import router as observability_router
from backend.api.llm import router as llm_router
from backend.api.orchestrator import router as orchestrator_router
from backend.api.orchestrator_durable import router as orchestrator_durable_router
from backend.api.memory import router as memory_router

settings = get_settings()

app = FastAPI(
    title="Assest — Company Brain",
    description="High-precision agentic knowledge retrieval engine.",
    version=settings.app_version,
    lifespan=app_lifespan,
)

# ── Custom Safety Middleware ─────────────────────────────
from starlette.types import ASGIApp, Scope, Receive, Send, Message
import re
import json

class ValueAlignmentMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        # Apply safety checks only on query, reasoning, and orchestrator routes
        if not any(prefix in path for prefix in ["/api/query", "/api/reasoning", "/api/orchestrator"]):
            await self.app(scope, receive, send)
            return

        accumulated_text = ""
        CREDENTIAL_PATTERNS = [
            (re.compile(r"(?i)(password|passwd|secret|apikey|api_key|client_secret|db_password)\s*[:=]\s*['\"][^'\"]{3,}['\"]"), r"\1: '[REDACTED]'"),
            (re.compile(r"(?i)bearer\s+[a-zA-Z0-9_\-\.]{15,}"), "Bearer [REDACTED]")
        ]

        def redact_text(text: str) -> str:
            for pattern, repl in CREDENTIAL_PATTERNS:
                text = pattern.sub(repl, text)
            return text

        is_sse = False

        async def send_wrapper(message: Message):
            nonlocal accumulated_text, is_sse
            if message["type"] == "http.response.start":
                headers = message.get("headers", [])
                for k, v in headers:
                    if k == b"content-type" and b"text/event-stream" in v:
                        is_sse = True
                        break
            elif message["type"] == "http.response.body":
                body = message.get("body", b"")

                if is_sse:
                    try:
                        decoded = body.decode("utf-8", errors="ignore")
                        lines = decoded.split("\n")
                        new_lines = []
                        for line in lines:
                            if line.startswith("data:"):
                                try:
                                    payload_str = line[5:].strip()
                                    payload = json.loads(payload_str)
                                    if payload.get("type") == "token":
                                        token = payload.get("token", "")
                                        accumulated_text += token
                                        redacted_accumulated = redact_text(accumulated_text)
                                        if redacted_accumulated != accumulated_text:
                                            sent_so_far = accumulated_text[:-len(token)] if len(token) <= len(accumulated_text) else ""
                                            redacted_sent = redact_text(sent_so_far)
                                            redacted_token = redacted_accumulated[len(redacted_sent):]
                                            payload["token"] = redacted_token
                                            accumulated_text = redacted_accumulated
                                        line = f"data: {json.dumps(payload)}"
                                except Exception:
                                    pass
                            new_lines.append(line)
                        message["body"] = "\n".join(new_lines).encode("utf-8")
                    except Exception:
                        pass
                else:
                    try:
                        decoded = body.decode("utf-8", errors="ignore")
                        try:
                            data = json.loads(decoded)
                            if isinstance(data, dict):
                                if "answer" in data and isinstance(data["answer"], str):
                                    data["answer"] = redact_text(data["answer"])
                                if "final_answer" in data and isinstance(data["final_answer"], str):
                                    data["final_answer"] = redact_text(data["final_answer"])
                            message["body"] = json.dumps(data).encode("utf-8")
                        except json.JSONDecodeError:
                            message["body"] = redact_text(decoded).encode("utf-8")
                    except Exception:
                        pass

            await send(message)

        await self.app(scope, receive, send_wrapper)

app.add_middleware(ValueAlignmentMiddleware)


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
app.include_router(auth_router, prefix="/api")
app.include_router(workspaces_router, prefix="/api")
app.include_router(documents_router, prefix="/api")
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

@app.api_route("/{path_name:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
async def catch_all(request: Request, path_name: str):
    print(f"DEBUG: CATCH-ALL hit: {request.method} /{path_name}")
    return {
        "error": "Not Found",
        "path": path_name,
        "method": request.method,
        "detail": f"Assest Catch-all: Route /{path_name} does not exist on this server."
    }
