#!/usr/bin/env bash
set -euo pipefail

# Run Assest backend without requiring a virtualenv activation.
# Usage: ./scripts/run.sh [bg]
#   bg - run in background (uses nohup)

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

# Ensure PYTHONPATH includes project root so 'backend' package resolves
export PYTHONPATH="$ROOT_DIR":${PYTHONPATH:-}

# Load .env if present
if [ -f .env ]; then
  echo "Loading .env"
  set -o allexport
  # shellcheck disable=SC1091
  source .env
  set +o allexport
fi

mkdir -p data

# Default host/port fallbacks (can be overridden in .env)
HOST=${app_host:-127.0.0.1}
PORT=${app_port:-8000}

CMD=(python3 -m uvicorn backend.main:app --host "$HOST" --port "$PORT")

if [ "${1:-}" = "bg" ]; then
  echo "Starting in background on http://$HOST:$PORT"
  nohup "${CMD[@]}" > logs/uvicorn.out 2>&1 &
  echo $! > run.pid
  echo "PID $(cat run.pid) written to run.pid"
else
  echo "Starting in foreground on http://$HOST:$PORT"
  exec "${CMD[@]}"
fi
