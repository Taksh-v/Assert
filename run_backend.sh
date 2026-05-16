#!/bin/bash

# Assest Backend Startup Script
echo "🧠 Starting Assest Brain Backend..."

# Set PYTHONPATH to include current directory
export PYTHONPATH=$PYTHONPATH:.

# Fix SSL Certification issues (common on macOS)
export SSL_CERT_FILE=$(python3 -c "import certifi; print(certifi.where())")
echo "🔒 SSL Certificates configured from: $SSL_CERT_FILE"

# Check if port 8000 is taken
if lsof -Pi :8000 -sTCP:LISTEN -t >/dev/null ; then
    echo "⚠️  Port 8000 is already in use. Attempting to kill the process..."
    lsof -ti:8000 | xargs kill -9
    sleep 1
fi

# Start Uvicorn
python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload --log-level info
