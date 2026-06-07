# Assest — Codebase Inventory

This file lists major components, where to find them, and a short description of their responsibilities.

## Top-level
- `backend/` — FastAPI backend, core services, agents, workers, and reasoning orchestration.
- `web/` — Next.js frontend UI for chat, conversation lists, and inspector.
- `data/` — Persistent data artifacts and local DB files used for development.
- `docs/` — Architecture docs and audit artifacts (this folder contains `architecture/`).
- `infrastructure/` — Docker-compose and infra scripts for local/dev deployment.
- `tests/` — Test suite (unit/integration) for backend components.

## Backend (detailed)
- `backend/main.py` — FastAPI entrypoint and application lifecycle (startup/shutdown).
- `backend/core/` — Core utilities and configuration
  - `config.py` — pydantic settings and environment mapping
  - `llm_impl.py` — SharedLLMClient and LLM routing/fallback logic
  - `database.py` — DB initialization helpers
- `backend/api/` — HTTP route handlers (query, auth, workspaces, connectors, health)
- `backend/query/` — Query service and streaming SSE endpoint
  - `query_service.py` — business logic and streaming contract
  - `semantic_cache.py` — cache layer for semantic answers
- `backend/reasoning/` — Reasoning orchestrator and multi-agent supervisors
  - `supervisor.py` — intent classification and agent routing
  - `agents/` — planner, analyst, synthesizer agent implementations
- `backend/generation/` — generation helpers and stream-to-client logic
- `backend/workers/` — background worker implementations and scheduler
- `backend/models/` — SQLAlchemy models for conversations, queries, users, etc.
- `backend/observability/` — telemetry and tracing helpers

## Frontend (detailed)
- `web/src/app/chat/[id]/page.tsx` — Chat UI streaming handling, SSE parsing
- `web/src/components/` — UI components used across pages
- `web/public/` — static assets

## Dev / infra
- `run.sh` / `run_backend.sh` — dev startup script (starts backend + frontend in dev mode)
- `infrastructure/docker-compose.yml` — local infra (qdrant, redis, db) if present
- `.env` / `.env.example` — runtime configuration (secrets cached in local `.env`)

## Tests
- `tests/unit/` — unit tests for backend components (LLM fallback tests added)
- `tests/e2e/` — end-to-end tests (some missing; to add streaming e2e)

## Observations / Quick wins
- Central LLM routing lives in `backend/core/llm_impl.py` — adding validation, retries, and fallbacks here yields high impact.
- SSE streaming contract is implemented in `backend/query/query_service.py` and consumed in `web/src/app/chat/[id]/page.tsx` — improving event variety (`status`, `token`, `sources`) immediately improves UX.
- Secrets hygiene: `.env` contained keys; `.env.example` and `.gitignore` were added — rotate any compromised keys.

---

File generated automatically as the first step of the audit-driven implementation.
