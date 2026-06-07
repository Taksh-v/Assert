#!/bin/bash

# Assest Backend Startup Script
echo "🧠 Starting Assest Brain Backend..."

# Set PYTHONPATH to include current directory
export PYTHONPATH=$PYTHONPATH:.

# Load .env if it exists (Ensures sub-processes like workers have them)
if [[ -f ".env" ]]; then
    set -a; source .env; set +a
fi

# Fix SSL Certification issues (common on macOS)
# We do this quickly without a full interpreter boot if we can
if [[ -z "${SSL_CERT_FILE:-}" ]]; then
    SSL_CERT_FILE=$(python3 -c "import certifi; print(certifi.where())" 2>/dev/null || echo "")
    if [[ -n "$SSL_CERT_FILE" ]]; then
        export SSL_CERT_FILE
        echo "🔒 SSL Certificates configured."
    fi
fi

# Check if port 8000 is taken
if lsof -Pi :8000 -sTCP:LISTEN -t >/dev/null ; then
    echo "⚠️  Port 8000 is already in use. Clearing..."
    lsof -ti:8000 | xargs kill -9 2>/dev/null || true
    sleep 1
fi

# Start Background Worker
echo "⚙️  Starting Background Worker Process..."
python3 backend/worker_main.py > logs/worker.log 2>&1 &
WORKER_PID=$!

# Trap SIGINT and SIGTERM to kill the worker when the script exits
trap "echo 'Stopping Background Worker...'; kill -TERM $WORKER_PID 2>/dev/null" EXIT

# Start Uvicorn with a single worker to prevent SQLite locking issues
echo "🚀 Starting Uvicorn Web Server..."
python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --workers 1 --log-level info
