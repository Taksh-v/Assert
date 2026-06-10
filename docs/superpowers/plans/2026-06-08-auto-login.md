# Auto-Login and Profile Persistence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automatically log in users after successful registration (Join) and ensure their full name is immediately persisted to show correctly in the sidebar profile.

**Architecture:**
1.  **AuthPortal Refactor**: Update the registration logic to chain a login request immediately after a successful `/api/register` call.
2.  **State Sync**: Ensure `setCurrentUser` is called with the full user object (including name) immediately after registration-login.
3.  **AppShell Re-render**: Rely on the existing `AUTH_CHANGE_EVENT` to trigger the switch from `AuthPortal` to the dashboard.

**Tech Stack:** Next.js, TypeScript

---

### Task 1: Implement Auto-Login after Registration

**Files:**
- Modify: `web/src/components/AuthPortal.tsx`

- [ ] **Step 1: Refactor handleSubmit to perform login after signup**

```tsx
// Find the registration block (else block of isLogin) and update it:

      } else {
        const response = await apiFetch("/api/register", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email, password, full_name: fullName }),
        });

        if (!response.ok) {
          const errData = await response.json().catch(() => ({}));
          throw new Error(errData.detail || "Registration failed.");
        }

        // --- NEW AUTO-LOGIN LOGIC ---
        setSuccess("Account created! Entering Brain...");
        
        // Wait briefly for backend to propagate if needed (optional)
        const loginParams = new URLSearchParams();
        loginParams.append("username", email);
        loginParams.append("password", password);

        const loginRes = await apiFetch("/api/login", {
          method: "POST",
          headers: { "Content-Type": "application/x-www-form-urlencoded" },
          body: loginParams,
        });

        if (!loginRes.ok) throw new Error("Auto-login failed. Please sign in manually.");

        const loginData = await loginRes.json();
        setAuthToken(loginData.access_token);

        // Fetch user info to get the ID and confirm Name
        const userRes = await apiFetch("/api/users/me", {
          headers: { Authorization: `Bearer ${loginData.access_token}` },
        });

        if (userRes.ok) {
          const userData = await userRes.json();
          setCurrentUser({
            id: userData.id,
            email: userData.email,
            full_name: userData.full_name || fullName, // Fallback to input name
          });

          // Fetch or Create Workspace
          const workspaceRes = await apiFetch("/api/workspaces", {
            headers: { Authorization: `Bearer ${loginData.access_token}` },
          });
          if (workspaceRes.ok) {
            const workspaces = await workspaceRes.json();
            if (workspaces.length > 0) setActiveWorkspace(workspaces[0]);
            else {
               const createWs = await apiFetch("/api/workspaces", {
                 method: "POST",
                 body: JSON.stringify({ name: "My Workspace" })
               });
               if (createWs.ok) setActiveWorkspace(await createWs.json());
            }
          }
        }
      }
```

- [ ] **Step 2: Commit**

```bash
git add web/src/components/AuthPortal.tsx
git commit -m "feat(auth): auto-login user after successful registration"
```
