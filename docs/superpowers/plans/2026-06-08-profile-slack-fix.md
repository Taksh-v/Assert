# Profile & Slack Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement interactive user profile in the sidebar with sign-out, fix the Slack connection error by passing OAuth state properly, and ensure the "Composer" greeting renders the user's name reliably.

**Architecture:** 
1.  Update `Sidebar.tsx` to handle a dropdown state for the user profile section, displaying details and a sign-out button using `lucide-react` icons.
2.  Update `page.tsx`'s `getGreeting` logic to correctly fall back and rely on the synchronized user state so "there" is only used as a last resort, but primarily it should render the user's actual name.
3.  Update `backend/api/connectors.py` to securely pass the `state` token to the frontend during the OAuth initiation for Slack, ensuring parity with Notion and Google.
4.  Update `AppShell.tsx` and auth functions to ensure state sync is reliable.

**Tech Stack:** Next.js (React), TailwindCSS, FastAPI, Python

---

### Task 1: Fix Slack OAuth State Missing Token

**Files:**
- Modify: `backend/api/connectors.py`

- [ ] **Step 1: Write minimal implementation to add state to Slack OAuth**

```python
# In backend/api/connectors.py, modify the /oauth/authorize/{source_type} endpoint's slack section:

        if not settings.slack_client_id:
            raise HTTPException(status_code=400, detail="Slack OAuth is not configured. Please set SLACK_CLIENT_ID in .env")
        scopes = "channels:history,channels:read,users:read"
        return {
            "url": (
                f"https://slack.com/oauth/v2/authorize"
                f"?client_id={settings.slack_client_id}"
                f"&scope={scopes}"
                f"&redirect_uri={settings.slack_redirect_uri}"
                f"&state={create_oauth_state(workspace_id or 'default-workspace')}"
            ),
            "configured": True,
        }
```

- [ ] **Step 2: Commit**

```bash
git add backend/api/connectors.py
git commit -m "fix(slack): pass OAuth state token during authorization"
```

### Task 2: Implement Interactive Profile & Sign Out in Sidebar

**Files:**
- Modify: `web/src/components/Sidebar.tsx`

- [ ] **Step 1: Write the minimal implementation for profile dropdown and sign out**

```tsx
// Inside web/src/components/Sidebar.tsx
// Add import for LogOut from lucide-react and signOut from auth
import { MessageSquare, Link2, Brain, Plus, Trash2, Home, BarChart3, LogOut, ChevronDown } from "lucide-react";
import { apiFetch, getActiveWorkspace, getCurrentUser, isAdminWorkspaceRole, signOut } from "@/lib/auth";

// Add state for dropdown
const [showProfileMenu, setShowProfileMenu] = useState(false);

// Add click outside listener
useEffect(() => {
  const handleClickOutside = (e: MouseEvent) => {
    const target = e.target as HTMLElement;
    if (!target.closest('.profile-menu-container')) {
      setShowProfileMenu(false);
    }
  };
  if (showProfileMenu) document.addEventListener('click', handleClickOutside);
  return () => document.removeEventListener('click', handleClickOutside);
}, [showProfileMenu]);

const handleSignOut = () => {
  setShowProfileMenu(false);
  signOut();
  router.push("/");
};

// ... In the JSX, replace the profile container with this ...
        {/* Profile & Workspace metadata (Merged Top Panel) */}
        <div className="relative profile-menu-container">
          <button 
            onClick={() => setShowProfileMenu(!showProfileMenu)}
            className="w-full text-left rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-3 flex items-center justify-between shadow-md hover:border-[var(--border-focus)] transition-all duration-300 group"
          >
            <div className="flex items-center gap-2.5 overflow-hidden">
              <div className="h-7 w-7 rounded bg-[var(--bg-surface-hover)] border border-[var(--border-subtle)] flex items-center justify-center text-[10px] font-bold text-[var(--text-primary)] shrink-0 font-mono relative">
                {initials}
                <span className="absolute bottom-[-1px] right-[-1px] h-2 w-2 rounded-full border border-[var(--bg-surface)] bg-[var(--success)] shadow-[0_0_6px_var(--success)]" />
              </div>
              <div className="flex flex-col overflow-hidden min-w-0">
                <span className="text-[11px] font-semibold text-[var(--text-primary)] truncate font-display tracking-tight group-hover:text-[var(--accent)] transition-colors duration-200">
                  {user?.full_name || user?.email?.split("@")[0] || "User"}
                </span>
                <span className="text-[9px] font-mono text-[var(--text-muted)] truncate flex items-center gap-1.5 mt-0.5 uppercase tracking-wider">
                  <span>{workspace?.name || "WORKSPACE"}</span>
                  {isAdmin && <span className="text-[8px] font-bold text-[var(--success)] bg-[var(--success-muted)] px-1 rounded border border-[var(--success)]/10 font-mono">ADM</span>}
                </span>
              </div>
            </div>
            <ChevronDown className={`h-3.5 w-3.5 text-[var(--text-muted)] transition-transform duration-200 ${showProfileMenu ? "rotate-180" : ""}`} />
          </button>

          {/* Dropdown Menu */}
          {showProfileMenu && (
            <div className="absolute top-full left-0 right-0 mt-2 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] shadow-lg z-50 overflow-hidden animate-fade-in origin-top">
              <div className="p-3 border-b border-[var(--border-subtle)]/40 bg-[var(--bg-root)]/50">
                <p className="text-[10px] font-semibold text-[var(--text-primary)] truncate">{user?.full_name || "User"}</p>
                <p className="text-[9px] font-mono text-[var(--text-muted)] truncate mt-0.5">{user?.email}</p>
              </div>
              <div className="p-1.5">
                <button
                  onClick={handleSignOut}
                  className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-[10px] font-semibold uppercase tracking-wider text-[var(--danger)] hover:bg-[var(--danger)]/10 transition-colors duration-200"
                >
                  <LogOut className="h-3.5 w-3.5" />
                  Sign Out
                </button>
              </div>
            </div>
          )}
        </div>
```

- [ ] **Step 2: Commit**

```bash
git add web/src/components/Sidebar.tsx
git commit -m "feat(ui): add interactive profile dropdown and sign out"
```

### Task 3: Fix Greeting Name Rendering 

**Files:**
- Modify: `web/src/app/page.tsx`

- [ ] **Step 1: Write minimal implementation to ensure real name renders**

```tsx
// Inside web/src/app/page.tsx
// Find getGreeting and update it to parse user correctly. It was only returning 'there' before if state loading was slightly delayed.

// Update getGreeting to handle fallback better
function getGreeting(name: string) {
  const hr = new Date().getHours();
  let base = "Good night";
  
  if (hr >= 5 && hr < 12) base = "Good morning";
  else if (hr >= 12 && hr < 17) base = "Good afternoon";
  else if (hr >= 17 && hr < 21) base = "Good evening";
  
  const displayName = name && name !== "there" ? name : "";
  
  return (
    <h1 className="text-2xl font-bold tracking-tight text-[var(--text-primary)] sm:text-3xl font-display">
      {base}{displayName ? `, ${displayName}` : ""}
    </h1>
  );
}

// In ChatPage component, ensure userName falls back gracefully but updates when user loads
// The variable is currently:
// const userName = user?.full_name || user?.email?.split("@")[0] || "there";
// Update to just use empty string fallback so the comma is dropped, or actual name.
const userName = user?.full_name || user?.email?.split("@")[0] || "";
```

- [ ] **Step 2: Commit**

```bash
git add web/src/app/page.tsx
git commit -m "fix(ui): personalize composer greeting and drop generic there"
```
