# Assest Frontend

Next.js workspace console for Assest. The production shape is:

- Browser talks to the same-origin Next route handler at `/api/backend/*`.
- The route handler forwards requests to FastAPI using server-only `ASSEST_API_URL`.
- Auth tokens stay user-scoped through `Authorization`; optional service auth uses `ASSEST_BACKEND_API_KEY`.
- Build verification runs TypeScript, ESLint, and `next build`.

## Getting Started

Create local frontend env:

```bash
cp .env.example .env.local
```

Start the backend on `http://localhost:8000`, then run:

```bash
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

## Production Readiness

Required production env:

```bash
ASSEST_API_URL=https://api.example.com
NEXT_PUBLIC_API_BASE_PATH=/api/backend
ASSEST_BACKEND_API_KEY=
```

Do not set browser-visible backend origins unless clients should call FastAPI directly. Prefer the server-side adapter so CORS, API key injection, and backend topology stay outside the browser bundle.

Before shipping:

```bash
npm run verify
```

Deploy as a Node.js server or container. `next.config.ts` uses `output: "standalone"` so Docker and VM deployments can run the minimal Next server output.

## Operational Checks

- `/api/backend/health` should return backend health.
- The home dashboard and Observability HUD should show backend health and metric samples.
- Login/register should go through `/api/backend/login` and `/api/backend/register`.
- Streaming chat should go through `/api/backend/query/stream`.
