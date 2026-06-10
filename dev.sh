#!/bin/bash

# Assest Fast Dev Runner
# ─────────────────────────────────────────────────────

set -euo pipefail

# 1. Run Health Check & Env Sync
echo "🩺 Running Assest Doctor..."
python3 scripts/doctor.py

# 2. Setup Mode
MODE=${1:-"default"}
if [ "$MODE" == "sandbox" ]; then
    echo "🧪 Entering SANDBOX mode (Local SQLite, Local Storage)"
    export ASSEST_DEV_MODE="sandbox"
    export QDRANT_MODE="memory"
fi

# 3. Start services with interleaved logs
echo "🚀 Starting services..."

# Clean up function
cleanup() {
    echo "Stopping..."
    kill $(jobs -p) 2>/dev/null || true
    exit
}
trap cleanup SIGINT SIGTERM

# Start Backend
./run_backend.sh > logs/backend.log 2>&1 &
echo "✅ Backend started (logs in logs/backend.log)"

# Wait for backend
echo -n "⏳ Waiting for backend..."
until curl -s http://localhost:8000/health/live > /dev/null; do
    echo -n "."
    sleep 1
done
echo " Live!"

# Start Frontend
(cd web && npm run dev) &
echo "✅ Frontend started on http://localhost:3000"

# Optional: Stream logs
echo "📖 Streaming logs (Ctrl+C to stop)..."
tail -f logs/backend.log
