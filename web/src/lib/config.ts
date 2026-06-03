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

