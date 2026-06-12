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

# Set environment variables for production (remove first to avoid "already exists" errors)
echo -e "${CYAN}Step 2: Configuring environment variables...${NC}"
npx -y vercel env rm ASSEST_API_URL production -y || true
npx -y vercel env add ASSEST_API_URL production <<< "https://Taxyhere-assest-brain.hf.space"

npx -y vercel env rm NEXT_PUBLIC_API_BASE_PATH production -y || true
npx -y vercel env add NEXT_PUBLIC_API_BASE_PATH production <<< "/api/backend"

npx -y vercel env rm NEXT_PUBLIC_SITE_URL production -y || true
npx -y vercel env add NEXT_PUBLIC_SITE_URL production <<< "https://web-kappa-eight-88.vercel.app"

npx -y vercel env rm NEXT_PUBLIC_SUPABASE_URL production -y || true
npx -y vercel env add NEXT_PUBLIC_SUPABASE_URL production <<< "https://mayvqbzbuqhvmjxyvdib.supabase.co"

npx -y vercel env rm NEXT_PUBLIC_SUPABASE_ANON_KEY production -y || true
npx -y vercel env add NEXT_PUBLIC_SUPABASE_ANON_KEY production <<< "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im1heXZxYnpidXFodm1qeHl2ZGliIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzkyODcwNDMsImV4cCI6MjA5NDg2MzA0M30.6Wu3kv4tt5x3uhHHnEtLHsB8pYSuRUjD-J6dJz7AxPk"

# Deploy to production
echo -e "${CYAN}Step 3: Deploying to Vercel...${NC}"
npx -y vercel --prod \
  --build-env ASSEST_API_URL="https://Taxyhere-assest-brain.hf.space" \
  --build-env NEXT_PUBLIC_API_BASE_PATH="/api/backend" \
  --build-env NEXT_PUBLIC_SITE_URL="https://web-kappa-eight-88.vercel.app" \
  --build-env NEXT_PUBLIC_SUPABASE_URL="https://mayvqbzbuqhvmjxyvdib.supabase.co" \
  --build-env NEXT_PUBLIC_SUPABASE_ANON_KEY="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im1heXZxYnpidXFodm1qeHl2ZGliIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzkyODcwNDMsImV4cCI6MjA5NDg2MzA0M30.6Wu3kv4tt5x3uhHHnEtLHsB8pYSuRUjD-J6dJz7AxPk"

echo -e "${GREEN}✅ Frontend deployed to Vercel!${NC}"
echo -e "${CYAN}Your app is live at the URL shown above.${NC}"
