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

cd web

# 2. Deploy to production with inline environment variables
# This is MUCH faster than setting them one by one via 'vercel env add'
echo -e "${CYAN}Step 2: Deploying to Vercel Production...${NC}"
npx -y vercel --prod --yes \
  --build-env ASSEST_API_URL="https://Taxyhere-assest-brain.hf.space" \
  --build-env NEXT_PUBLIC_API_BASE_PATH="/api/backend" \
  --build-env NEXT_PUBLIC_SITE_URL="https://web-kappa-eight-88.vercel.app" \
  --build-env NEXT_PUBLIC_SUPABASE_URL="https://mayvqbzbuqhvmjxyvdib.supabase.co" \
  --build-env NEXT_PUBLIC_SUPABASE_ANON_KEY="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im1heXZxYnpidXFodm1qeHl2ZGliIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzkyODcwNDMsImV4cCI6MjA5NDg2MzA0M30.6Wu3kv4tt5x3uhHHnEtLHsB8pYSuRUjD-J6dJz7AxPk"

echo -e "${GREEN}✅ Frontend deployed to Vercel!${NC}"
