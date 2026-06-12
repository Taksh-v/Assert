const DEFAULT_BROWSER_API_BASE_PATH = "/api/backend";
const DEFAULT_DEV_BACKEND_URL = "http://localhost:8000";

function trimTrailingSlash(value: string) {
  return value.replace(/\/+$/, "");
}

export function getBrowserApiBasePath() {
  const configured = process.env.NEXT_PUBLIC_API_BASE_PATH || DEFAULT_BROWSER_API_BASE_PATH;
  return trimTrailingSlash(configured);
}

export function getServerBackendUrl() {
  const configured = process.env.ASSEST_API_URL || process.env.NEXT_PUBLIC_API_URL;

  if (configured) {
    return trimTrailingSlash(configured);
  }

  if (process.env.NODE_ENV !== "production") {
    return DEFAULT_DEV_BACKEND_URL;
  }

  throw new Error("ASSEST_API_URL must be set for production frontend deployments.");
}

export function getSiteUrl() {
  // 1. Explicitly configured site URL (best for production)
  if (process.env.NEXT_PUBLIC_SITE_URL) {
    return trimTrailingSlash(process.env.NEXT_PUBLIC_SITE_URL);
  }

  // 2. Vercel deployment URL (automatic for preview/prod on Vercel)
  if (process.env.NEXT_PUBLIC_VERCEL_URL) {
    return `https://${process.env.NEXT_PUBLIC_VERCEL_URL}`;
  }

  // 3. Browser runtime origin (fallback for dynamic environments)
  if (typeof window !== "undefined") {
    return window.location.origin;
  }

  // 4. Default for local development
  return "http://localhost:3000";
}

