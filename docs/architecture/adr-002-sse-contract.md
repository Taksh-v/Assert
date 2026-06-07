# ADR 002 — SSE Contract and Frontend Fallbacks

Status: Accepted

Context
-------
SSE streaming is used to deliver assistant content progressively to the frontend. The frontend previously only rendered `token` events and ignored `status` or `error`, leading to silent UIs if tokens weren't emitted.

Decision
--------
Define an explicit SSE event schema and frontend rendering rules:

- Event schema: JSON payload with `type` in {`conversation`, `status`, `token`, `error`, `done`} and `request_id` present on every event.
- Backend guarantees at least one `token` emission at the end of a stream. If no semantic tokens are available, backend will emit a fallback `token` with a friendly message.
- Frontend must render `status` events as interim UI signals (spinner + inline message) and render `error` events visibly.
- Frontend should merge partial/chunked `token` events into a single assistant message as they arrive.

Consequences
------------
- More robust UX: users see progress even when the LLM fails to stream tokens.
- Slightly more backend responsibility to ensure token fallback semantics.

Implementation Notes
--------------------
- Files: `backend/query/query_service.py`, `web/src/app/chat/[id]/page.tsx`.
- Tests: `tests/e2e/test_streaming.py` asserts `status` or `token` delivered within timeout.
