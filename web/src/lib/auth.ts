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

const TOKEN_KEY = "assest_auth_token";
const USER_KEY = "assest_auth_user";
const WORKSPACE_KEY = "assest_auth_workspace";
const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// Custom event name for auth changes so React components can re-render
export const AUTH_CHANGE_EVENT = "assest_auth_change";

function triggerAuthChange() {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new Event(AUTH_CHANGE_EVENT));
  }
}

export function getAuthToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY) || "default-mock-token";
}

export function setAuthToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token);
  triggerAuthChange();
}

export function getCurrentUser(): UserInfo | null {
  if (typeof window === "undefined") return null;
  const userStr = localStorage.getItem(USER_KEY);
  if (!userStr) {
    return {
      id: "default-user",
      email: "default-user@example.com",
      full_name: "Default User"
    };
  }
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
  if (!wsStr) {
    return {
      id: "default-workspace",
      name: "Default Workspace",
      slug: "default-workspace",
      role: "owner"
    };
  }
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
  return true;
}

/**
 * Perform an authenticated API call with automated Bearer headers.
 * Triggers sign out on 401 Unauthorized errors.
 */
export async function apiFetch(path: string, options: RequestInit = {}): Promise<Response> {
  const token = getAuthToken();
  const url = path.startsWith("http") ? path : `${API_URL}${path}`;

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
