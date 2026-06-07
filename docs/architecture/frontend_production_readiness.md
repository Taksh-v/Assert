# Frontend Production Readiness

Status: Implemented baseline

## Required Runtime Shape

The frontend should be deployed as a Next.js Node server or container, not as a static export. It relies on a route-handler adapter at `/api/backend/*` for authenticated API traffic and streaming responses.

Browser traffic:

```text
Browser -> Next.js app -> /api/backend/* -> FastAPI /api/*
```

This keeps backend topology, service API keys, and CORS policy out of the browser bundle while preserving user-scoped bearer auth.

## Required Environment

Production must set:

```bash
ASSEST_API_URL=https://api.example.com
NEXT_PUBLIC_API_BASE_PATH=/api/backend
```

Optional:

```bash
ASSEST_BACKEND_API_KEY=
```

Avoid `NEXT_PUBLIC_API_URL` in production unless there is an intentional decision for browsers to call FastAPI directly.

## Industry-Ready Frontend Baseline

- Same-origin backend adapter for query, auth, connector, metrics, and streaming routes.
- `next.config.ts` disables `x-powered-by`, enables strict React checks, emits standalone output, and applies basic security headers.
- Route-level `error.tsx`, `loading.tsx`, and `not-found.tsx` provide recoverable production UI states.
- `npm run verify` runs TypeScript, ESLint, and production build.
- `/api/backend/health` is the frontend-facing health smoke test for backend reachability.

## Release Gate

Run from `web/`:

```bash
npm run verify
```

Then manually smoke test:

- Sign in through `/api/backend/login`.
- Load dashboard health and connector state.
- Start a chat and verify `/api/backend/query/stream` delivers status, token, metadata, and done events.
- Open Observability HUD and verify health/metrics render without browser CORS errors.

