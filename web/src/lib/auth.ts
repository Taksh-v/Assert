export interface UserInfo {
  id: string;
  email: string;
  full_name?: string;
}

export interface WorkspaceInfo {
  id: string;
  name: string;
  slug: string;
  role: string;
}

export function isAdminWorkspaceRole(role?: string | null): boolean {
  return role === "owner" || role === "admin";
}

import { getBrowserApiBasePath } from "./config";

const TOKEN_KEY = "assest_identity_v1";
const USER_KEY = "assest_auth_user";
const WORKSPACE_KEY = "assest_auth_workspace";

// Custom event name for auth changes so React components can re-render
export const AUTH_CHANGE_EVENT = "assest_auth_change";

function triggerAuthChange() {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new Event(AUTH_CHANGE_EVENT));
  }
}

let cachedToken: string | null = null;
let tokenExpiry = 0;

/**
 * Retrieves the currently active authentication token from memory or local storage.
 */
export async function getAuthToken(): Promise<string | null> {
  if (typeof window === "undefined") return null;

  // Use memory cache if token is less than 5 minutes old
  if (cachedToken && Date.now() < tokenExpiry) {
    return cachedToken;
  }

  const localToken = localStorage.getItem(TOKEN_KEY);
  if (localToken) {
    cachedToken = localToken;
    tokenExpiry = Date.now() + 5 * 60 * 1000;
  }
  return cachedToken;
}

export function setAuthToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token);
  cachedToken = token;
  tokenExpiry = Date.now() + 5 * 60 * 1000;
}

export function getCurrentUser(): UserInfo | null {
  if (typeof window === "undefined") return null;
  const userStr = localStorage.getItem(USER_KEY);
  if (!userStr) return null;
  try {
    return JSON.parse(userStr) as UserInfo;
  } catch {
    return null;
  }
}

export function setCurrentUser(user: UserInfo) {
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

/**
 * Atomically commits the full authenticated session (token + user + workspace)
 * and fires a single auth-change event.
 */
export function commitSession(
  token: string,
  user: UserInfo,
  workspace?: WorkspaceInfo | null
) {
  localStorage.setItem(TOKEN_KEY, token);
  cachedToken = token;
  tokenExpiry = Date.now() + 5 * 60 * 1000;

  localStorage.setItem(USER_KEY, JSON.stringify(user));

  if (workspace) {
    localStorage.setItem(WORKSPACE_KEY, JSON.stringify(workspace));
  }

  triggerAuthChange();
}

export function getActiveWorkspace(): WorkspaceInfo | null {
  if (typeof window === "undefined") return null;
  const wsStr = localStorage.getItem(WORKSPACE_KEY);
  if (!wsStr) return null;
  try {
    return JSON.parse(wsStr) as WorkspaceInfo;
  } catch {
    return null;
  }
}

export function setActiveWorkspace(workspace: WorkspaceInfo) {
  localStorage.setItem(WORKSPACE_KEY, JSON.stringify(workspace));
  triggerAuthChange();
}

export async function signOut() {
  cachedToken = null;
  tokenExpiry = 0;

  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
  localStorage.removeItem(WORKSPACE_KEY);

  triggerAuthChange();
}

export async function isAuthenticated(): Promise<boolean> {
  if (typeof window === "undefined") return false;
  const token = await getAuthToken();
  if (!token) return false;

  if (getCurrentUser()) return true;

  try {
    const res = await apiFetch("/users/me");
    if (res.ok) {
      const userData = await res.json() as UserInfo;
      localStorage.setItem(USER_KEY, JSON.stringify(userData));
      await ensureDefaultWorkspace().catch(() => {});
      return true;
    }
    return false;
  } catch (err) {
    return false;
  }
}

export async function ensureDefaultWorkspace(): Promise<WorkspaceInfo | null> {
  const existing = getActiveWorkspace();
  if (existing) return existing;

  try {
    const res = await apiFetch("/workspaces");
    if (!res.ok) return null;
    const workspaces = await res.json() as WorkspaceInfo[];
    
    if (workspaces && workspaces.length > 0) {
      const defaultWs = {
        id: workspaces[0].id,
        name: workspaces[0].name,
        slug: workspaces[0].slug,
        role: workspaces[0].role || "owner"
      };
      setActiveWorkspace(defaultWs);
      return defaultWs;
    }
  } catch (err) {
    console.error("Failed to auto-select workspace:", err);
  }
  return null;
}

function toBackendProxyPath(path: string) {
  if (path.startsWith("http")) {
    return path;
  }

  const apiBasePath = getBrowserApiBasePath();
  const backendPath = path.startsWith("/api/") ? path.slice(4) : path;
  const normalizedPath = backendPath.startsWith("/") ? backendPath : `/${backendPath}`;
  return `${apiBasePath}${normalizedPath}`;
}

export async function apiFetch(path: string, options: RequestInit = {}): Promise<Response> {
  const token = await getAuthToken();
  const url = toBackendProxyPath(path);

  const headers = new Headers(options.headers || {});
  
  // Only add the cached token if no Authorization header was explicitly provided
  if (token && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  
  if (!headers.has("Content-Type") && !(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(url, {
    ...options,
    headers,
  });

  if (response.status === 401) {
    const hasSession = typeof window !== "undefined" && !!localStorage.getItem(TOKEN_KEY);
    if (!path.includes("/users/me") && hasSession) {
      signOut();
    }
  }

  return response;
}
