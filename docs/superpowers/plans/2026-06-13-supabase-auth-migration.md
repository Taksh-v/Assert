# Supabase Auth Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate from internal JWT auth to Supabase Auth with shadow user syncing.

**Architecture:** 
- Frontend uses Supabase SDK for auth.
- Backend verifies Supabase JWTs using `SUPABASE_JWT_SECRET`.
- Backend syncs Supabase users to local DB on first request.

**Tech Stack:** Supabase SDK, FastAPI, Python-Jose.

---

### Task 1: Backend Token Verification

**Files:**
- Modify: `backend/api/users.py`
- Modify: `backend/core/config.py` (ensure `supabase_jwt_secret` is used)

- [ ] **Step 1: Update get_current_user to handle Supabase JWTs**

```python
# In backend/api/users.py
async def get_current_user(...):
    # Try Supabase verification first
    if settings.supabase_jwt_secret:
        try:
            payload = jwt.decode(token, settings.supabase_jwt_secret, algorithms=["HS256"], audience="authenticated")
            supabase_id = payload.get("sub")
            email = payload.get("email")
            # Sync user if not exists
            # ...
        except JWTError:
            pass
```

---

### Task 2: Frontend Client Setup

**Files:**
- Modify: `web/package.json`
- Create: `web/src/lib/supabase.ts`

- [ ] **Step 1: Install dependencies**
Run: `npm install @supabase/supabase-js`

- [ ] **Step 2: Create Supabase client**

```typescript
import { createClient } from '@supabase/supabase-js'
export const supabase = createClient(process.env.NEXT_PUBLIC_SUPABASE_URL!, process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!)
```

---

### Task 3: Update AuthPortal

**Files:**
- Modify: `web/src/components/AuthPortal.tsx`

- [ ] **Step 1: Replace apiFetch("/api/login") with supabase.auth.signInWithPassword**
- [ ] **Step 2: Replace apiFetch("/api/register") with supabase.auth.signUp**
- [ ] **Step 3: Add "Forgot Password" UI and supabase.auth.resetPasswordForEmail**

---

### Task 4: Handle Password Reset Callback

**Files:**
- Create: `web/src/app/auth/reset-password/page.tsx`

- [ ] **Step 1: Implement password update page**
Using `supabase.auth.updateUser({ password })`.
