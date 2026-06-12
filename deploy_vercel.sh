#!/bin/bash
# ──────────────────────────────────────────────────────────────
# Assest Frontend → Optimized Vercel Deployment Script
# ──────────────────────────────────────────────────────────────
set -e

BLUE='\033[0;34m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${BLUE}🚀 Deploying Assest Frontend to Vercel...${NC}"

# 1. Check if logged in, otherwise login
if ! npx -y vercel whoami > /dev/null 2>&1; then
  echo -e "${CYAN}Logging into Vercel...${NC}"
  npx -y vercel login
fi

# 2. Deploy to production
echo -e "${CYAN}Step 2: Deploying to Vercel Production...${NC}"

# Ensure we are in the web directory
[[ "$PWD" != */web ]] && cd web

npx -y vercel --prod --yes

echo -e "${GREEN}✅ Frontend deployed to Vercel!${NC}"

