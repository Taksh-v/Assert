# Design Spec: Supabase Auth & Chat-Integrated Document Uploads

**Date:** 2026-06-09
**Status:** Draft
**Topic:** Re-implementing Google Auth via Supabase and moving document uploads from Connectors to Chat.

## 1. Objectives
- Replace the broken manual Google OAuth with a production-grade Supabase Auth implementation.
- Move document uploads from the "Connectors" page to the Chat interface for a more natural UX (similar to ChatGPT/Claude).
- Ensure chat-uploaded documents are workspace-wide and available for grounding in all conversations.

## 2. Architecture

### 2.1 Authentication (Supabase)
- **Frontend Integration**: 
  - Install `@supabase/supabase-js`.
  - Create a shared `supabase` client in `web/src/lib/supabase.ts`.
  - Update `AuthPortal.tsx` to use `supabase.auth.signInWithOAuth({ provider: 'google' })`.
- **Backend Verification**:
  - Backend will verify the `Authorization: Bearer <JWT>` header using the Supabase JWT secret (or public keys).
  - `get_current_user` in `backend/api/users.py` will be updated to extract the user email and ID from the Supabase payload.

### 2.2 Document Ingestion (Chat)
- **New Endpoint**: `POST /api/documents/upload`
  - Accepts `multipart/form-data` (file) and `workspace_id`.
  - Saves file to storage (local or Supabase Storage).
  - Triggers the `HybridParser` and `VectorStore.upsert_documents` immediately.
- **Frontend Changes**:
  - Add an attachment icon to `web/src/app/page.tsx` (Homepage Composer) and `web/src/app/chat/[id]/page.tsx` (Chat Input).
  - Implement a progress indicator for the upload/ingestion phase.
- **Connector Cleanup**:
  - Remove `file_upload` from `web/src/app/connectors/page.tsx`.
  - Deprecate/Remove `backend/connectors/file_upload.py` if no longer needed for legacy syncs.

## 3. Data Flow

### Auth Flow
1. User -> Click "Login with Google" -> Supabase OAuth -> Google Handshake.
2. Google -> Redirect to `/auth/callback` -> Supabase Client sets session.
3. Frontend -> `apiFetch` includes Supabase JWT in headers.
4. Backend -> Verifies JWT -> Resolves `current_user`.

### Upload Flow
1. User -> Drag & Drop file to Chat -> Frontend `POST /api/documents/upload`.
2. Backend -> Save bytes -> Call `HybridParser.parse()`.
3. Backend -> `VectorStore.upsert_documents()` -> Grounding DB updated.
4. Frontend -> Show "Document Indexed" success state -> User asks question.

## 4. Security & Constraints
- **File Limits**: Enforce 50MB limit per file.
- **Access Control**: Ensure files uploaded in `workspace_A` are only available to users with access to `workspace_A`.
- **Secrets**: Use `SUPABASE_URL`, `SUPABASE_ANON_KEY`, and `SUPABASE_JWT_SECRET` in `.env`.
