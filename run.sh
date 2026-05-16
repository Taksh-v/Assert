#!/bin/bash

# Assest — System Startup Script
# Orchestrates Backend (FastAPI) and Frontend (Next.js)

# Colors for better visibility
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}🧠 Assest Brain — Starting System...${NC}"

# Create logs directory if it doesn't exist
mkdir -p logs

# Function to handle cleanup on exit
cleanup() {
    echo -e "\n${YELLOW}🛑 Shutting down services...${NC}"
    kill $BACKEND_PID 2>/dev/null
    kill $FRONTEND_PID 2>/dev/null
    echo -e "${GREEN}✅ Services stopped.${NC}"
    exit 0
}

# Trap SIGINT (Ctrl+C) and SIGTERM
trap cleanup SIGINT SIGTERM

# 1. Environment Check
echo -e "${BLUE}🔍 Checking environment...${NC}"

# User requested no venv - using system python
echo -e "   ✅ Using system Python (no venv)..."

if [ ! -d "web/node_modules" ]; then
    echo -e "   ${YELLOW}⚠️  web/node_modules not found. Running npm install...${NC}"
    cd web && npm install && cd ..
fi

# 2. Start Backend
echo -e "${BLUE}🚀 Starting Backend (FastAPI)...${NC}"
export PYTHONPATH=$PYTHONPATH:$(pwd)
export GRPC_DNS_RESOLVER=native

# [FIX] Set SSL Certificates for macOS (critical for Slack/Notion)
export SSL_CERT_FILE=$(python3 -c "import certifi; print(certifi.where())")
echo -e "   🔒 SSL Certificates configured: $SSL_CERT_FILE"

# [FIX] Clean up port 8000 if it's taken
if lsof -Pi :8000 -sTCP:LISTEN -t >/dev/null ; then
    echo -e "   ⚠️  Cleaning up port 8000..."
    lsof -ti:8000 | xargs kill -9
    sleep 1
fi

# Using system python directly
python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload > logs/backend.log 2>&1 &
BACKEND_PID=$!

# Wait a bit for backend to start
sleep 2
if ps -p $BACKEND_PID > /dev/null; then
    echo -e "   ✅ Backend started (PID: $BACKEND_PID). Logs: logs/backend.log"
else
    echo -e "   ${RED}❌ Backend failed to start. Check logs/backend.log${NC}"
    exit 1
fi

# 3. Start Frontend
echo -e "${BLUE}🚀 Starting Frontend (Next.js)...${NC}"
cd web
npm run dev -- -p 3000 > ../logs/frontend.log 2>&1 &
FRONTEND_PID=$!
cd ..

# Wait a bit for frontend to start
sleep 2
if ps -p $FRONTEND_PID > /dev/null; then
    echo -e "   ✅ Frontend started (PID: $FRONTEND_PID). Logs: logs/frontend.log"
else
    echo -e "   ${RED}❌ Frontend failed to start. Check logs/frontend.log${NC}"
    kill $BACKEND_PID
    exit 1
fi

echo -e "\n${GREEN}✨ System is up and running!${NC}"
echo -e "   🔗 Backend:  ${BLUE}http://localhost:8000${NC}"
echo -e "   🔗 API Docs: ${BLUE}http://localhost:8000/docs${NC}"
echo -e "   🔗 Frontend: ${BLUE}http://localhost:3000${NC}"
echo -e "\n${YELLOW}Press Ctrl+C to stop all services.${NC}"

# Keep script running to maintain processes
wait
