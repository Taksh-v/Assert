#!/bin/bash
# ──────────────────────────────────────────────────────────────
# Assest Frontend → Vercel Deployment Script
# Run this from the project root: ./deploy_vercel.sh
# ──────────────────────────────────────────────────────────────
set -e

BLUE='\033[0;34m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${BLUE}🚀 Deploying Assest Frontend to Vercel...${NC}"

# 1. Login to Vercel (opens browser)
echo -e "${CYAN}Step 1: Logging into Vercel (a browser window will open)...${NC}"
npx -y vercel login

# 2. Link project and deploy
echo -e "${CYAN}Step 2: Deploying web/ directory to Vercel...${NC}"
cd web

# Set environment variables for production
npx -y vercel env add ASSEST_API_URL production <<< "https://Taxyhere-assest-brain.hf.space"
npx -y vercel env add NEXT_PUBLIC_API_BASE_PATH production <<< "/api/backend"

# Deploy to production
npx -y vercel --prod \
  --build-env ASSEST_API_URL="https://Taxyhere-assest-brain.hf.space" \
  --build-env NEXT_PUBLIC_API_BASE_PATH="/api/backend"

echo -e "${GREEN}✅ Frontend deployed to Vercel!${NC}"
echo -e "${CYAN}Your app is live at the URL shown above.${NC}"
