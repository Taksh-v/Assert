# Supabase Auth & Chat Uploads Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace broken Google OAuth with Supabase and integrate workspace-wide document uploads directly into the chat interface.

**Architecture:** 
1. **Auth:** Shift from manual OAuth to Supabase Auth on the frontend, with backend JWT verification.
2. **Ingestion:** Create a direct document upload API that bypasses the "Connector" sync cycle for immediate ingestion.
3. **UI:** Add attachment support to both the landing page composer and the active chat thread.

**Tech Stack:** Next.js (Frontend), FastAPI (Backend), Supabase Auth, `@supabase/supabase-js`, `python-jose` (JWT).

---

## Part 1: Supabase Google Auth Implementation

### Task 1: Initialize Supabase Client (Frontend)

**Files:**
- Create: `web/src/lib/supabase.ts`
- Modify: `web/package.json`

- [ ] **Step 1: Install dependencies**
  Run: `cd web && npm install @supabase/supabase-js`

- [ ] **Step 2: Create supabase client**
  Create: `web/src/lib/supabase.ts`
```typescript
import { createClient } from '@supabase/supabase-js';

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL || '';
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || '';

export const supabase = createClient(supabaseUrl, supabaseAnonKey);
```

- [ ] **Step 3: Commit**
```bash
git add web/package.json web/src/lib/supabase.ts
git commit -m "feat: init supabase client"
```

### Task 2: Implement Google Login UI

**Files:**
- Modify: `web/src/components/AuthPortal.tsx`
- Modify: `web/src/lib/auth.ts`

- [ ] **Step 1: Update AuthPortal.tsx**
  Replace the `handleGoogleLogin` function with:
```typescript
const handleGoogleLogin = async () => {
  const { error } = await supabase.auth.signInWithOAuth({
    provider: 'google',
    options: {
      redirectTo: `${window.location.origin}/auth/callback`,
    },
  });
  if (error) console.error("Google login error:", error.message);
};
```

- [ ] **Step 2: Update auth.ts to handle Supabase sessions**
  Modify `web/src/lib/auth.ts` to include a helper that retrieves the Supabase JWT for `apiFetch` calls.

- [ ] **Step 3: Commit**
```bash
git add web/src/components/AuthPortal.tsx web/src/lib/auth.ts
git commit -m "feat: implement supabase google login ui"
```

### Task 3: Backend JWT Verification

**Files:**
- Modify: `backend/core/config.py`
- Modify: `backend/api/users.py`
- Modify: `backend/requirements.txt`

- [ ] **Step 1: Install JWT library**
  Add `python-jose[cryptography]` to `backend/requirements.txt` and run install.

- [ ] **Step 2: Add Supabase secrets to config**
  Update `backend/core/config.py` to include `supabase_jwt_secret`.

- [ ] **Step 3: Update get_current_user**
  Modify `backend/api/users.py` to decode and verify the JWT from the `Authorization` header using the Supabase secret.

- [ ] **Step 4: Commit**
```bash
git add backend/core/config.py backend/api/users.py backend/requirements.txt
git commit -m "feat: backend supabase jwt verification"
```

---

## Part 2: Chat-Integrated Document Uploads

### Task 4: Backend Document Upload API

**Files:**
- Create: `backend/api/documents.py`
- Modify: `backend/main.py`

- [ ] **Step 1: Create upload endpoint**
  Create `backend/api/documents.py` with a `POST /upload` endpoint that uses `HybridParser` and `VectorStore` to ingest files immediately.

- [ ] **Step 2: Register router**
  Add the new documents router to `backend/main.py`.

- [ ] **Step 3: Commit**
```bash
git add backend/api/documents.py backend/main.py
git commit -m "feat: chat upload api endpoint"
```

### Task 5: Frontend Chat Upload UI

**Files:**
- Modify: `web/src/app/page.tsx`
- Modify: `web/src/app/chat/[id]/page.tsx`

- [ ] **Step 1: Add upload button to Homepage**
  Modify `web/src/app/page.tsx` to add a `Paperclip` icon to the composer that triggers a file selection dialog.

- [ ] **Step 2: Implement upload logic**
  Call the new `/api/documents/upload` endpoint when a file is selected. Show a loading spinner during ingestion.

- [ ] **Step 3: Add upload button to Chat Thread**
  Modify `web/src/app/chat/[id]/page.tsx` to add the same upload capability to the follow-up input.

- [ ] **Step 4: Commit**
```bash
git add web/src/app/page.tsx web/src/app/chat/[id]/page.tsx
git commit -m "feat: chat upload ui integration"
```

### Task 6: Cleanup Connectors

**Files:**
- Modify: `web/src/app/connectors/page.tsx`

- [ ] **Step 1: Remove File Upload connector**
  Remove `file_upload` from the `CONNECTOR_METADATA` map in `web/src/app/connectors/page.tsx`.

- [ ] **Step 2: Commit**
```bash
git add web/src/app/connectors/page.tsx
git commit -m "cleanup: remove legacy file upload connector ui"
```
