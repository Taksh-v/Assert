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
import { supabase } from "./supabase";

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

export async function getAuthToken(): Promise<string | null> {
  if (typeof window === "undefined") return null;

  // Use memory cache if token is less than 5 minutes old
  if (cachedToken && Date.now() < tokenExpiry) {
    return cachedToken;
  }

  try {
    const { data: { session } } = await supabase.auth.getSession();
    if (session?.access_token) {
      cachedToken = session.access_token;
      // Cache for 5 minutes
      tokenExpiry = Date.now() + 5 * 60 * 1000;
      return cachedToken;
    }
  } catch (err) {
    console.warn("Failed to get Supabase session:", err);
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

export async function signOut() {
  // 1. Immediate local memory purge
  cachedToken = null;
  tokenExpiry = 0;

  // 2. Clear all local storage
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
  localStorage.removeItem(WORKSPACE_KEY);

  // 3. Fire Supabase signout (non-blocking for the UI redirect)
  supabase.auth.signOut().catch(err => console.error("Supabase signout error:", err));

  // 4. Hard redirect to home to flush all React state/closures
  // Avoid infinite reload loop if already on the home page
  if (typeof window !== "undefined") {
    if (window.location.pathname !== "/") {
      window.location.href = "/";
    } else {
      // If already on /, just trigger the change event to update AppShell
      triggerAuthChange();
    }
  }
}

export async function isAuthenticated(): Promise<boolean> {
  if (typeof window === "undefined") return false;
  const token = await getAuthToken();
  if (!token) return false;

  // Hydrate local user profile if it's missing (e.g. after Google OAuth redirect)
  if (!getCurrentUser()) {
    console.log("[Auth] User profile missing, attempting to hydrate from backend...");
    try {
      // Use a controller to prevent infinite hang if backend is slow
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 10000); // 10s timeout

      const res = await apiFetch("/users/me", { signal: controller.signal });
      clearTimeout(timeoutId);

      if (res.ok) {
        const userData = await res.json() as UserInfo;
        console.log("[Auth] Successfully hydrated user profile:", userData.email);
        setCurrentUser(userData);
        await ensureDefaultWorkspace();
      } else {
        console.error("[Auth] Failed to hydrate user profile. Status:", res.status);
        // If profile hydration fails, we are essentially not authenticated for the app's purposes
        return false;
      }
    } catch (err) {
      console.error("Failed to auto-hydrate user session:", err);
      return false;
    }
  }

  return true;
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
  const token = await getAuthToken();
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
    // Only trigger sign out if we're not already trying to check authentication
    // to prevent infinite reloading loops when the backend rejects a token.
    if (!path.includes("/users/me")) {
      signOut();
    }
  }

  return response;
}
