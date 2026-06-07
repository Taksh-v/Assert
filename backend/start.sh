#!/bin/bash
# Assest Backend & Worker Startup Script for Production Docker Container
# ───────────────────────────────────────────────────────────────────────

# Fail fast
set -e

echo "🧠 Starting Assest Production Services..."

# 1. Start the Background Worker in the background
# It processes scheduled loops (Memory synthesis, DLQ retries) and handles the Slack Socket Mode Bot.
echo "⚙️ Starting Background Worker Process..."
python -u backend/worker_main.py &
WORKER_PID=$!

# Ensure the worker process is killed when this shell script exits
trap "echo 'Stopping worker process (PID $WORKER_PID)...'; kill -TERM $WORKER_PID 2>/dev/null || true" EXIT

# 2. Start Uvicorn API Server in the foreground
# Using exec allows Docker/Koyeb/Render to propagate lifecycle signals (SIGTERM/SIGINT) directly to Uvicorn.
echo "🚀 Starting Uvicorn Web Server on port ${PORT:-8000}..."
exec python -m uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --log-level info
