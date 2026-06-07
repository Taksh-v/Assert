# System Hardening and Reasoning Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Secure the system against tenant data leakage, fix reasoning amnesia by integrating working memory, and replace stubbed skills with real implementations.

**Architecture:** 
- **Security:** Deepen the `VectorStore` interface to enforce `workspace_id` at the lowest retrieval seam.
- **Reasoning:** Integrate `WorkingMemory` into the `Orchestrator` to provide multi-turn context awareness.
- **Capability:** Implement real Skill adapters in the `Dispatcher` using the formal `SkillContractMixin`.
- **Governance:** Apply `PIIScrubber` to inputs before LLM processing to prevent sensitive data leakage to providers.

**Tech Stack:** FastAPI, Qdrant, SQLAlchemy, LiteLLM, Presidio.

---

### Task 1: Fix Vector Leakage (CRITICAL Security)

**Files:**
- Modify: `backend/core/vector_store.py`
- Test: `backend/tests/test_vector_isolation.py`

- [ ] **Step 1: Write a failing test for cross-tenant retrieval**
```python
import pytest
from backend.core.vector_store import VectorStore

def test_vector_search_isolation():
    vs = VectorStore()
    # Mock some data for WS_A and WS_B if needed, 
    # or just verify the filter logic in the search call
    # Here we will check if workspace_id is in must_filters
```

- [ ] **Step 2: Run test to verify it fails**
Run: `pytest backend/tests/test_vector_isolation.py`
Expected: FAIL or manual inspection shows missing filter.

- [ ] **Step 3: Implement workspace_id enforcement in search**
Modify `backend/core/vector_store.py`:
```python
# In search method
must_filters = [
    self._models.FieldCondition(key="workspace_id", match=self._models.MatchValue(value=workspace_id)),
    self._models.FieldCondition(key="is_active", match=self._models.MatchValue(value=True))
]
```

- [ ] **Step 4: Run test to verify it passes**
Run: `pytest backend/tests/test_vector_isolation.py`

---

### Task 2: Fix Reasoning Amnesia (Orchestrator ↔ WorkingMemory)

**Files:**
- Modify: `backend/orchestrator/orchestrator.py`
- Create: `backend/tests/test_multi_turn_reasoning.py`

- [ ] **Step 1: Update Orchestrator to accept conversation_id and load history**
```python
from backend.memory.working import WorkingMemory
# ... in run()
self.working_memory = WorkingMemory()
# ... fetch history from DB using conversation_id
```

- [ ] **Step 2: Incorporate history summary into Planner context**
```python
summary = await self.working_memory.summarize_history(history)
context["history_summary"] = summary
```

- [ ] **Step 3: Write test for multi-turn awareness**
Verify that the planner receives context from previous turns.

---

### Task 3: Implement Real Knowledge Search Skill

**Files:**
- Modify: `backend/orchestrator/dispatcher.py`
- Modify: `backend/connectors/base.py` (add SkillContractMixin)

- [ ] **Step 1: Wire internal_knowledge_search to real QueryService**
Ensure it uses the Semantic Layer metadata if available.

---

### Task 4: Input PII Scrubbing (Governance)

**Files:**
- Modify: `backend/orchestrator/orchestrator.py`

- [ ] **Step 1: Scrub user query BEFORE passing to Planner**
```python
# In run()
clean_query, _ = self.scrubber.scrub(query)
plan = await self.planner.create_plan(clean_query, context)
```

---

### Task 5: Final System Audit & Benchmark

- [ ] **Step 1: Run `scripts/agent_benchmarks.py`**
Verify improved success rate and correct skill usage.
