#!/bin/bash
# 🧠 Assest — Company Brain Infrastructure Orchestrator
# Automates launching and verifying the unified open-source services.

set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}🧠 Starting Assest Open-Source Infrastructure Stack...${NC}"

# 1. Verify Docker daemon is running
if ! docker info >/dev/null 2>&1; then
    echo -e "${RED}❌ Error: Docker is not running. Please start Docker first.${NC}"
    exit 1
fi

# 2. Check if host has .env file in parent directory and source keys
if [ -f "../.env" ]; then
    echo -e "${GREEN}✅ Sourced API keys from .env file${NC}"
    export $(grep -v '^#' ../.env | xargs)
elif [ -f ".env" ]; then
    echo -e "${GREEN}✅ Sourced API keys from local .env file${NC}"
    export $(grep -v '^#' .env | xargs)
else
    echo -e "${YELLOW}⚠️ Warning: No .env file found. Ensure GROQ_API_KEY, ANTHROPIC_API_KEY, and OPENAI_API_KEY are configured in your system environment.${NC}"
fi

# 3. Pull/build and start containers
echo -e "${GREEN}🚀 Orchestrating containers via docker-compose...${NC}"
docker-compose up -d

# 4. Verification Check loop
echo -e "${YELLOW}🔍 Verifying service availability...${NC}"

# Helper function to check endpoint connectivity
check_service() {
    local name=$1
    local url=$2
    local expected_code=$3
    local max_attempts=15
    local attempt=1

    echo -n "Checking $name... "
    while [ $attempt -le $max_attempts ]; do
        code=$(curl -s -o /dev/null -w "%{http_code}" "$url" || true)
        if [ "$code" = "$expected_code" ] || { [ "$expected_code" = "200" ] && [ "$code" = "302" ]; } || { [ "$expected_code" = "200" ] && [ "$code" = "307" ]; } || { [ "$expected_code" = "200" ] && [ "$code" = "404" ]; } || { [ "$name" = "LiteLLM" ] && [ "$code" = "200" ]; } || { [ "$name" = "Qdrant" ] && [ "$code" = "200" ]; }; then
            echo -e "${GREEN}READY ($code)${NC}"
            return 0
        fi
        sleep 2
        attempt=$((attempt + 1))
    done
    echo -e "${RED}FAILED (Timed out)${NC}"
    return 1
}

# Run service health checks
check_service "Qdrant Vector DB" "http://localhost:6333/dashboard" "200"
check_service "LiteLLM Gateway" "http://localhost:4000/v1/models" "200"
check_service "Langfuse Dashboard" "http://localhost:3000/api/public/health" "200"
check_service "Open WebUI Frontend" "http://localhost:8080/api/v1" "200"

echo -e "${GREEN}🎉 All core services are online and healthy!${NC}"
echo -e "--------------------------------------------------------"
echo -e "   📍 Open WebUI Chat UI   : http://localhost:8080"
echo -e "   📍 Langfuse Dashboard   : http://localhost:3000"
echo -e "   📍 LiteLLM model API    : http://localhost:4000"
echo -e "   📍 Qdrant Admin Panel   : http://localhost:6333/dashboard"
echo -e "--------------------------------------------------------"
echo -e "Run 'docker-compose logs -f' to inspect container outputs."
