# Autonomous Architecture Upgrade Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. 

**Goal:** Transform the codebase into a robust, modern AI architecture with strict separation of concerns, semantic caching, and resilient background task execution.

**Architecture:** Hexagonal architecture for the API, Semantic Caching pattern for LLM optimization, and an Outbox/Job Queue pattern for background resilience.

---

### Task 1: Decouple API from Business Logic (Hexagonal Architecture)

**Files:**
- Create: `backend/query/query_service.py`
- Modify: `backend/api/query.py`
- Test: `backend/tests/test_query_service.py`

- [ ] **Step 1:** Create `QueryService` class in `backend/query/query_service.py`. Move the logic from the `/query` and `/query/stream` endpoints (intent classification, agent routing, orchestration) into this service.
- [ ] **Step 2:** Refactor `backend/api/query.py` to only handle HTTP validation, dependency injection, and calling `QueryService`.
- [ ] **Step 3:** Write tests for `QueryService` ensuring it correctly routes intents without relying on FastAPI request objects.

### Task 2: Implement Semantic Caching

**Files:**
- Create: `backend/query/semantic_cache.py`
- Modify: `backend/query/query_service.py`
- Test: `backend/tests/test_semantic_cache.py`

- [ ] **Step 1:** Create `SemanticCache` using `backend.core.vector_store.VectorStore` or a lightweight DB table to store `(query_embedding, response, intent)` tuples.
- [ ] **Step 2:** Integrate `SemanticCache` into `QueryService`. Before running orchestrators, check the cache. If similarity > 0.95, return cached response. If miss, execute and save to cache.
- [ ] **Step 3:** Write tests for cache hits and misses.

### Task 3: Resilient Event-Driven Task Management (DB Queue)

**Files:**
- Create: `backend/workers/task_queue.py`
- Modify: `backend/api/connectors.py`
- Modify: `backend/core/database.py` (Add BackgroundTask model)
- Test: `backend/tests/test_task_queue.py`

- [ ] **Step 1:** Add a `BackgroundTask` SQLAlchemy model to `database.py` (status: pending, processing, failed, completed; retry_count).
- [ ] **Step 2:** Create `backend/workers/task_queue.py` with `enqueue_task` and a worker loop `process_tasks`.
- [ ] **Step 3:** Refactor `backend/api/connectors.py` (`trigger_sync`) to use `enqueue_task` instead of `asyncio.create_task`.
- [ ] **Step 4:** Write tests verifying tasks are queued and processed.