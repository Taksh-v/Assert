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

export function getAuthToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function setAuthToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token);
  triggerAuthChange();
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

export function signOut() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
  localStorage.removeItem(WORKSPACE_KEY);
  triggerAuthChange();
}

export function isAuthenticated(): boolean {
  if (typeof window === "undefined") return false;
  return !!localStorage.getItem(TOKEN_KEY);
}

/**
 * Ensures that an active workspace is set in local storage.
 * If none exists, fetches from /api/workspaces and sets the first one.
 */
export async function ensureDefaultWorkspace(): Promise<WorkspaceInfo | null> {
  try {
    const res = await apiFetch("/workspaces");
    if (!res.ok) return null;
    const workspaces = await res.json() as WorkspaceInfo[];
    
    if (workspaces && workspaces.length > 0) {
      const current = getActiveWorkspace();
      const stillExists = current ? workspaces.some(w => w.id === current.id) : false;
      if (stillExists && current) {
        return current;
      }

      const defaultWs = {
        id: workspaces[0].id,
        name: workspaces[0].name,
        slug: workspaces[0].slug,
        role: "owner"
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

/**
 * Perform an authenticated API call with automated Bearer headers.
 * Triggers sign out on 401 Unauthorized errors.
 */
export async function apiFetch(path: string, options: RequestInit = {}): Promise<Response> {
  const token = getAuthToken();
  const url = toBackendProxyPath(path);

  const headers = new Headers(options.headers || {});
  if (token) {
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
    // Session expired or invalid token
    signOut();
  }

  return response;
}
