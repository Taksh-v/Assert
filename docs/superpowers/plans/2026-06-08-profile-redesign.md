# Profile Redesign & Slack OAuth Fix Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Relocate and redesign the profile section to the bottom of the sidebar, fix persistent Slack OAuth errors by ensuring `workspace_id` is always passed, and ensure the profile menu is easily accessible.

**Architecture:**
1.  **Sidebar Refactor**: Move the `profile-menu-container` logic from the top to the bottom of `Sidebar.tsx`.
2.  **Modern Profile Card**: Implement a compact, high-density profile card at the bottom of the sidebar (Avatar + Name + Email + Chevron).
3.  **OAuth Hardening**: Update `SourceSetupModal.tsx` to guard against empty `workspaceId` when calling the authorization endpoint.
4.  **Auth Routing**: Ensure the application correctly redirects to the login view if no session is found, preventing the "can't see sign in" issue.

**Tech Stack:** Next.js (React), TailwindCSS, FastAPI (Python)

---

### Task 1: Harden OAuth Workspace Selection

**Files:**
- Modify: `web/src/components/SourceSetupModal.tsx`

- [ ] **Step 1: Prevent OAuth initiation without workspaceId**

```tsx
// In handleOAuth function:
const handleOAuth = async () => {
  if (!workspaceId) {
    setErrorMessage("No active workspace selected. Please select one before connecting.");
    return;
  }
  setIsLoading(true);
  // ... rest of code
```

- [ ] **Step 2: Commit**

```bash
git add web/src/components/SourceSetupModal.tsx
git commit -m "fix(oauth): guard against missing workspaceId"
```

### Task 2: Redesign and Relocate Profile to Sidebar Bottom

**Files:**
- Modify: `web/src/components/Sidebar.tsx`

- [ ] **Step 1: Move Profile Section to Bottom**

```tsx
// 1. Remove the profile section from the top of the sidebar JSX.
// 2. Add a flex-1 div to push content down.
// 3. Add the redesigned profile card at the bottom, inside the main nav container but after the scroll area.

// Updated JSX Structure:
<div className="flex h-full flex-col">
  {/* Top: Branding/Logo */}
  <div className="p-4">...</div>

  {/* Middle: Navigation (Scrollable) */}
  <div className="flex-1 overflow-y-auto px-3 py-2">...</div>

  {/* Bottom: Redesigned Profile Card */}
  <div className="mt-auto border-t border-[var(--border-subtle)]/40 p-3">
    <div className="relative profile-menu-container">
       {/* Compact Profile Card */}
       <button 
         onClick={() => setShowProfileMenu(!showProfileMenu)}
         className="flex w-full items-center gap-3 rounded-xl p-2 transition-colors hover:bg-[var(--bg-surface-hover)] group"
       >
         <div className="h-8 w-8 shrink-0 overflow-hidden rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-root)] flex items-center justify-center font-mono text-[10px] font-bold">
           {initials}
         </div>
         <div className="flex flex-col items-start overflow-hidden text-left">
           <span className="truncate text-xs font-semibold text-[var(--text-primary)]">
             {user?.full_name || "User"}
           </span>
           <span className="truncate text-[10px] text-[var(--text-muted)] group-hover:text-[var(--text-secondary)] transition-colors">
             {user?.email}
           </span>
         </div>
         <ChevronDown className={`ml-auto h-3.5 w-3.5 text-[var(--text-muted)] transition-transform duration-200 ${showProfileMenu ? "rotate-180" : ""}`} />
       </button>
       
       {/* Menu remains same but opens UPWARD or is positioned relative to bottom */}
       {showProfileMenu && (
         <div className="absolute bottom-full left-0 right-0 mb-2 ...">
           {/* Menu Content */}
         </div>
       )}
    </div>
  </div>
</div>
```

- [ ] **Step 2: Commit**

```bash
git add web/src/components/Sidebar.tsx
git commit -m "feat(ui): move and redesign profile card to sidebar bottom"
```

### Task 3: Ensure Greeting and Auth State Consistency

**Files:**
- Modify: `web/src/app/page.tsx`
- Modify: `web/src/components/AppShell.tsx`

- [ ] **Step 1: Verify auth redirect logic**

Ensure `AppShell.tsx` correctly renders `AuthPortal` when `!auth`. Check if `AuthPortal` has all fields for "Sign In".

- [ ] **Step 2: Fix greeting in page.tsx**

Ensure the greeting uses the `user` object directly from `getCurrentUser()` to avoid delay-based fallback to empty string.

- [ ] **Step 3: Commit**

```bash
git add web/src/app/page.tsx web/src/components/AppShell.tsx
git commit -m "fix(ui): ensure auth state and greeting consistency"
```
