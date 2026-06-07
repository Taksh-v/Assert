# Architectural Hardening and AI Safety Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Secure the system against tenant isolation leaks, cache poisoning, and data desync while improving worker performance.

**Architecture:** Middleware-based security, Parallel Job Execution, and Atomic Persistence with Blocking Evals.

---

### Task 1: Secure the Ingest API and Workspace Access

**Files:**
- Modify: `backend/api/ingest.py`
- Modify: `backend/api/query.py`
- Test: `backend/tests/test_security_audit.py`

- [ ] **Step 1:** Add `@Depends(get_current_user)` and `verify_workspace_access` to all endpoints in `backend/api/ingest.py`. It currently allows anyone to trigger ingestion.
- [ ] **Step 2:** Audit all routers in `backend/api/` and ensure `verify_workspace_access` is applied before any business logic.
- [ ] **Step 3:** Write a test that attempts to call `/api/ingest` without a token and verifies it returns 401.

### Task 2: Parallel Task Execution and Rate Limiting

**Files:**
- Modify: `backend/workers/task_queue.py`
- Test: `backend/tests/test_task_queue_saturation.py`

- [ ] **Step 1:** Refactor `process_tasks` to use an `asyncio.Semaphore(10)` and `asyncio.gather()` (or similar) to process up to 10 tasks in parallel, rather than one-by-one.
- [ ] **Step 2:** Add a "heartbeat" or "lock" mechanism to `BackgroundTask` so multiple worker instances don't grab the same task.

### Task 3: Atomic Multi-Store Persistence (DLQ for Desync)

**Files:**
- Modify: `backend/ingestion/pipeline_v2.py` (KnowledgeStore)
- Test: `backend/tests/test_knowledge_store_resilience.py`

- [ ] **Step 1:** Update `KnowledgeStore.persist` to use a try-except block for each external store (Vector, Graph).
- [ ] **Step 2:** If one store fails, mark the `Document` status as `PARTIAL_SUCCESS` and enqueue a "Sync Repair" task to the `BackgroundTask` queue to retry only the failed part later.

### Task 4: Blocking AI Evaluation (Hallucination Gate)

**Files:**
- Modify: `backend/query/query_service.py`
- Create: `backend/evals/blocking_evaluator.py`
- Test: `backend/tests/test_hallucination_gate.py`

- [ ] **Step 1:** Create `BlockingEvaluator` which uses `backend/evals/faithfulness.py` or similar to score the answer against the retrieved sources.
- [ ] **Step 2:** In `QueryService.execute_query`, if the evaluation score is below 0.7, do NOT return the answer. Instead, retry the query or return a "I couldn't verify this information" message.
- [ ] **Step 3:** Do NOT save to `SemanticCache` if the evaluation fails. This prevents cache poisoning.