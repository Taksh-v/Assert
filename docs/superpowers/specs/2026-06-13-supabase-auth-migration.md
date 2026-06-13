# Supabase Auth Migration Design

## Goal
Replace the internal JWT authentication with Supabase Auth for better security, managed password recovery, and scalability.

## Architecture

### 1. Frontend (web/)
- Install `@supabase/supabase-js`.
- Update `web/src/components/AuthPortal.tsx` to use Supabase SDK for `signInWithPassword`, `signUp`, and `resetPasswordForEmail`.
- Update `web/src/lib/auth.ts` to store and manage the Supabase session token.

### 2. Backend (backend/)
- **Token Verification**: Update `get_current_user` in `backend/api/users.py` to decode Supabase JWTs.
  - Supabase tokens are signed with `SUPABASE_JWT_SECRET`.
  - The `sub` claim in the token is the `supabase_id`.
- **User Sync**: When the backend receives a valid Supabase token for a user that doesn't exist locally:
  - Create a shadow record in the local `users` table.
  - Link it via the `supabase_id` column.
- **Password Reset**: Supabase handles the email sending and token generation. The backend just needs to accept the new tokens.

### 3. Data Flow
1. User enters credentials in `AuthPortal`.
2. `AuthPortal` calls Supabase directly.
3. Supabase returns a JWT.
4. Frontend sends this JWT in the `Authorization: Bearer <token>` header to the backend.
5. Backend verifies the token using the shared `SUPABASE_JWT_SECRET`.
6. Backend looks up the user by `supabase_id`.

## Security
- Password recovery is managed by Supabase (Industry standard).
- Backend never sees the plain-text password during recovery.
- Local `hashed_password` becomes redundant for Supabase users but can be kept as a fallback.
