#!/bin/bash

# Assest — System Startup Script (System Python Optimized)
# Orchestrates Backend (FastAPI) + Frontend (Next.js)
# ─────────────────────────────────────────────────────

set -euo pipefail

export PYTHONUNBUFFERED=1

# ── Colors ─────────────────────────────────────────
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

echo -e "${BLUE}${BOLD}🧠 Assest Company Brain — Starting...${NC}"
echo -e "${CYAN}────────────────────────────────────────${NC}"

# ── Directories ────────────────────────────────────
mkdir -p logs

# ── Cleanup on exit ────────────────────────────────
cleanup() {
    echo -e "\n${YELLOW}🛑 Shutting down services...${NC}"
    # Kill process groups to ensure all children (npm, uvicorn) are gone
    [[ -n "${BACKEND_PID:-}" ]]  && kill -TERM -"$BACKEND_PID"  2>/dev/null || true
    [[ -n "${FRONTEND_PID:-}" ]] && kill -TERM -"$FRONTEND_PID" 2>/dev/null || true
    pkill -f "uvicorn backend.main:app" 2>/dev/null || true
    echo -e "${GREEN}✅ All services stopped.${NC}"
    exit 0
}
trap cleanup SIGINT SIGTERM

# ── Python environment detection ───────────────────
PYTHON_EXEC=$(which python3.12 2>/dev/null || which python3 2>/dev/null || echo "")

if [[ -z "$PYTHON_EXEC" ]]; then
    echo -e "${RED}❌ Python not found. Please install Python 3.10+.${NC}"
    exit 1
fi

echo -e "${BLUE}🐍 Runtime: $PYTHON_EXEC${NC}"

# ── Environment variables ──────────────────────────
export PYTHONPATH="${PWD}:${PYTHONPATH:-}"

# SSL certs (critical for macOS)
SSL_CERT=$($PYTHON_EXEC -c "import certifi; print(certifi.where())" 2>/dev/null || echo "")
if [[ -n "$SSL_CERT" ]]; then
    export SSL_CERT_FILE="$SSL_CERT"
    export REQUESTS_CA_BUNDLE="$SSL_CERT"
fi

# Load .env if it exists
if [[ -f ".env" ]]; then
    echo -e "   📄 Loading .env..."
    set -o allexport
    source .env
    set +o allexport
fi

echo -e "${CYAN}────────────────────────────────────────${NC}"

# ── Infrastructure Check ───────────────────────────
echo -e "${BLUE}🐳 Checking Infrastructure (Docker)...${NC}"
if command -v docker-compose &> /dev/null; then
    (cd infrastructure && docker-compose up -d)
    echo -e "   ✅ Docker containers starting/running."
    
    # Wait for critical infrastructure (Postgres and Qdrant)
    echo -e "   ⏳ Waiting for Postgres readiness..."
    READY=0
    for _ in $(seq 1 30); do
        if docker exec assest-postgres pg_isready -U postgres -d langfuse >/dev/null 2>&1; then
            READY=1
            break
        fi
        sleep 1
    done
    if [[ "$READY" -eq 1 ]]; then
        echo -e "   ✅ Postgres is ready."
    else
        echo -e "   ⚠️  Postgres health check failed (continuing anyway)..."
    fi
else
    echo -e "   ⚠️  docker-compose not found. Ensure containers (Qdrant, Redis, Postgres) are running."
fi

# ── Verify imports before starting ─────────────────
echo -e "${BLUE}🔍 Verifying critical dependencies...${NC}"
# Use importlib.util to check existence without full import execution where possible
$PYTHON_EXEC - <<'PYCHECK'
import importlib.util
import sys
failed = []
checks = [
    ("fastapi",              "FastAPI"),
    ("sqlalchemy",           "SQLAlchemy"),
    ("pydantic_settings",    "Pydantic Settings"),
    ("litellm",              "LiteLLM Brain Gateway"),
    ("qdrant_client",        "Qdrant vector DB"),
    ("dlt",                  "DLT Ingestion"),
    ("jose",                 "python-jose"),
    ("bcrypt",               "bcrypt"),
    ("aiosqlite",            "aiosqlite"),
    ("slack_bolt",           "Slack Bolt"),
    ("langfuse",             "Langfuse"),
    ("spacy",                "Spacy"),
]
for mod, label in checks:
    if importlib.util.find_spec(mod) is not None:
        print(f"   ✅ {label}")
    else:
        print(f"   ⚠️  {label} — Not found")
        failed.append(label)

if failed:
    print(f"\n   ⚠️  Missing packages: {', '.join(failed)}")
    print("   Try: pip install -r backend/requirements.txt")
PYCHECK

echo -e "${CYAN}────────────────────────────────────────${NC}"

# ── Clean up ports 8000 & 3000 ─────────────────────
if lsof -Pi :8000 -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo -e "${YELLOW}⚠️  Port 8000 in use — clearing...${NC}"
    lsof -ti:8000 | xargs kill -9 2>/dev/null || true
fi

if lsof -Pi :3000 -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo -e "${YELLOW}⚠️  Port 3000 in use — clearing...${NC}"
    lsof -ti:3000 | xargs kill -9 2>/dev/null || true
fi
sleep 1

# ── Start Backend ──────────────────────────────────
echo -e "${BLUE}🚀 Starting Backend (FastAPI on :8000)...${NC}"

# Reuse the dedicated backend startup script
set -m
./run_backend.sh > logs/backend.log 2>&1 &
BACKEND_PID=$!
set +m

# Wait for the backend health endpoint before starting the frontend.
echo -e "${BLUE}⏳ Waiting for backend to wake up...${NC}"
READY=0
for i in $(seq 1 90); do
    if curl -fsS http://localhost:8000/health/live >/dev/null 2>&1; then
        READY=1
        break
    fi
    if (( i % 10 == 0 )); then
        echo -e "   ...still waiting ($i/90s)..."
    fi
    sleep 1
done

if [[ "$READY" -ne 1 ]]; then
    echo -e "${RED}❌ Backend failed to start within 90s. See logs/backend.log${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Backend is live.${NC}"

# ── Start Frontend ─────────────────────────────────
echo -e "${BLUE}🚀 Starting Frontend (Next.js on :3000)...${NC}"

if [[ ! -d "web/node_modules" ]]; then
    echo -e "${YELLOW}⚠️  node_modules missing in /web — installing...${NC}"
    (cd web && npm install --silent)
    echo -e "   ✅ Dependencies installed."
fi

set -m
(cd web && npm run dev -- -p 3000) > logs/frontend.log 2>&1 &
FRONTEND_PID=$!
set +m

echo -e "${CYAN}────────────────────────────────────────${NC}"
echo -e "${GREEN}${BOLD}✨ Assest is running!${NC}"
echo -e "   🔗 Backend  : http://localhost:8000"
echo -e "   🔗 Frontend : http://localhost:3000"
echo -e "   🔗 Health   : http://localhost:8000/health"
echo -e "   🔗 Traces   : http://localhost:8000/api/traces"
echo -e "   📄 Logs     : logs/backend.log & logs/frontend.log"
echo -e "${CYAN}────────────────────────────────────────${NC}"

wait
