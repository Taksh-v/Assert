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

# 2. Deploy to production with inline environment variables
# We use both --env (runtime) and --build-env (build-time) to ensure
# Next.js Server Components and API routes have access to them.
echo -e "${CYAN}Step 2: Deploying to Vercel Production...${NC}"

# Ensure we are in the web directory
[[ "$PWD" != */web ]] && cd web

npx -y vercel --prod --yes \
  --env ASSEST_API_URL="$ASSEST_API_URL" \
  --env NEXT_PUBLIC_API_BASE_PATH="/api/backend" \
  --env NEXT_PUBLIC_SITE_URL="https://web-kappa-eight-88.vercel.app" \
  --env NEXT_PUBLIC_SUPABASE_URL="https://mayvqbzbuqhvmjxyvdib.supabase.co" \
  --env NEXT_PUBLIC_SUPABASE_ANON_KEY="$NEXT_PUBLIC_SUPABASE_ANON_KEY" \
  --env HF_TOKEN="$HF_TOKEN" \
  --env SUPABASE_JWT_SECRET="$SUPABASE_JWT_SECRET" \
  --build-env ASSEST_API_URL="$ASSEST_API_URL" \
  --build-env NEXT_PUBLIC_API_BASE_PATH="/api/backend" \
  --build-env NEXT_PUBLIC_SITE_URL="https://web-kappa-eight-88.vercel.app" \
  --build-env NEXT_PUBLIC_SUPABASE_URL="https://mayvqbzbuqhvmjxyvdib.supabase.co" \
  --build-env NEXT_PUBLIC_SUPABASE_ANON_KEY="$NEXT_PUBLIC_SUPABASE_ANON_KEY" \
  --build-env HF_TOKEN="$HF_TOKEN" \
  --build-env SUPABASE_JWT_SECRET="$SUPABASE_JWT_SECRET"

echo -e "${GREEN}✅ Frontend deployed to Vercel!${NC}"

