# Deep Ingestion Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor the procedural ingestion logic into a deep, testable, and modular transformation pipeline.

**Architecture:** A "Pipe and Filter" architecture where an `IngestionPackage` DTO flows through a sequence of `Transformers` (Normalizer, Parser, Scrubber, Classifier, Chunker, Embedder, Extractor) and is finally persisted by a unified `KnowledgeStore`.

**Tech Stack:** Python, SQLAlchemy, Qdrant (VectorStore), Neo4j/GraphStore.

---

### Task 1: Complete the Transformer Suite

**Files:**
- Modify: `backend/ingestion/pipeline_v2.py`
- Test: `backend/tests/test_transformers_v2.py`

- [ ] **Step 1: Implement ParserTransformer**
- [ ] **Step 2: Implement ScrubberTransformer**
- [ ] **Step 3: Implement ClassifierTransformer**
- [ ] **Step 4: Implement ChunkerTransformer**
- [ ] **Step 5: Implement EmbedderTransformer**
- [ ] **Step 6: Implement ExtractorTransformer**

### Task 2: Unified KnowledgeStore

**Files:**
- Modify: `backend/ingestion/pipeline_v2.py`
- Test: `backend/tests/test_knowledge_store_v2.py`

- [ ] **Step 1: Implement KnowledgeStore that wraps SQL, Vector, and Graph persistence**

### Task 3: IngestionRunner and Pipeline Templates

**Files:**
- Modify: `backend/ingestion/pipeline_v2.py`
- Test: `backend/tests/test_ingestion_runner_v2.py`

- [ ] **Step 1: Implement PipelineTemplate and IngestionRunner**

### Task 4: Integration and Migration

**Files:**
- Modify: `backend/ingestion/pipeline.py`
- Test: `backend/tests/test_e2e_ingestion_v2.py`

- [ ] **Step 1: Switch IngestionPipeline to use the new IngestionRunner**
- [ ] **Step 2: Verify full system with end-to-end tests**
