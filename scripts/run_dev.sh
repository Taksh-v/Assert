#!/usr/bin/env bash
set -euo pipefail

# Simple dev runner for Assest backend
# Usage: bash scripts/run_dev.sh

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

if [ -f .env ]; then
  echo "Loading .env"
  # Export all variables declared in .env
  set -o allexport
  # shellcheck disable=SC1091
  source .env
  set +o allexport
fi

if [ -f venv/bin/activate ]; then
  echo "Activating virtualenv"
  # shellcheck disable=SC1091
  source venv/bin/activate
fi

mkdir -p data

# Respect pydantic settings names (app_host/app_port) if provided
APP_HOST=${app_host:-127.0.0.1}
APP_PORT=${app_port:-8000}

echo "Starting dev server at http://$APP_HOST:$APP_PORT"
uvicorn backend.main:app --reload --host "$APP_HOST" --port "$APP_PORT"
