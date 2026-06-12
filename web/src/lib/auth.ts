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
  // NOTE: Do NOT call triggerAuthChange() here.
  // Use commitSession() to atomically set token + user + workspace
  // and fire a single event when everything is ready.
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
  // NOTE: Don't fire triggerAuthChange here directly.
  // Call triggerAuthChange() manually after all session state is committed,
  // or use commitSession() for the full atomic flow.
}

/**
 * Atomically commits the full authenticated session (token + user + workspace)
 * and fires a single auth-change event. This is the ONLY place that should
 * trigger AppShell to re-check authentication after a login flow completes.
 */
export function commitSession(
  token: string,
  user: UserInfo,
  workspace?: WorkspaceInfo | null
) {
  // 1. Write everything to storage synchronously before any event fires
  localStorage.setItem(TOKEN_KEY, token);
  cachedToken = token;
  tokenExpiry = Date.now() + 5 * 60 * 1000;

  localStorage.setItem(USER_KEY, JSON.stringify(user));

  if (workspace) {
    localStorage.setItem(WORKSPACE_KEY, JSON.stringify(workspace));
  }

  // 2. Fire a single event now that everything is in place
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
  // Fire auth change so components can react to workspace switches
  // (e.g. switching workspaces from the sidebar — not the initial login).
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

  // Fast path: user profile already in localStorage — no network needed
  if (getCurrentUser()) return true;

  // Try to reconstruct from Supabase session metadata (zero-latency, no backend call)
  console.log("[Auth] User profile missing — trying Supabase metadata first...");
  try {
    const { data: { session } } = await supabase.auth.getSession();
    if (session?.user) {
      const userMeta = session.user.user_metadata ?? {};
      const userInfo: UserInfo = {
        id: session.user.id,
        email: session.user.email ?? "",
        full_name: userMeta.full_name || userMeta.name || session.user.email,
      };
      // Write to storage WITHOUT triggering auth change (we're already inside the check)
      localStorage.setItem(USER_KEY, JSON.stringify(userInfo));
      console.log("[Auth] Hydrated from Supabase metadata:", userInfo.email);
      // Kick off workspace load in background; don't block auth check
      ensureDefaultWorkspace().catch(() => {});
      return true;
    }
  } catch (err) {
    console.warn("[Auth] Could not get Supabase session:", err);
  }

  // Last resort: hit the backend /users/me (handles email/password JWTs)
  console.log("[Auth] Falling back to backend hydration...");
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 8000);
    const res = await apiFetch("/users/me", { signal: controller.signal });
    clearTimeout(timeoutId);

    if (res.ok) {
      const userData = await res.json() as UserInfo;
      console.log("[Auth] Backend hydration success:", userData.email);
      localStorage.setItem(USER_KEY, JSON.stringify(userData));
      ensureDefaultWorkspace().catch(() => {});
      return true;
    }

    console.error("[Auth] Backend hydration failed. Status:", res.status);
    return false;
  } catch (err) {
    console.error("[Auth] Backend hydration error:", err);
    return false;
  }
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
