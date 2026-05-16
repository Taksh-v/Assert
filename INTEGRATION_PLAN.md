# Strategic Integration: LangGraph & Langflow in Assest

## Executive Summary
Integrating **LangGraph** and **Langflow** will transform the Assest "Company Brain" from a linear RAG pipeline into a **Dynamic Reasoning Agent**. While our current custom infrastructure is optimized for high-performance ingestion (Layers 1-15), LangGraph provides the perfect framework for the **Agentic Orchestration (Layer 16)**.

---

## 1. LangGraph: The Multi-Agent Orchestration Layer
**Target: Layer 16 (Agentic Memory & Reasoning)**

### The "Researcher-Critic" Pattern
Instead of a single LLM call, we will implement a cyclic graph:
1.  **Search Node**: Uses our Hybrid Retriever to find chunks.
2.  **Graph Verifier Node**: Queries the `GraphStore` (Memgraph) to check if the retrieved chunks conflict with known organizational relationships.
3.  **Critic Node**: Evaluates the answer for groundedness. If hallucinations are detected, it signals the Search Node to find more specific context.

### Benefits for Assest:
- **Self-Correction**: Automatically fixes retrieval gaps before the user sees them.
- **Stateful Memory**: Natively handles episodic memory (what the user said 5 turns ago) and semantic memory (user preferences) using LangGraph Checkpointers.
- **HITL (Human-in-the-loop)**: Essential for **Property 4 (Permissioned)**. If a query hits a "Highly Sensitive" document, LangGraph can pause execution until a human admin approves the retrieval.

---

## 2. Langflow: The Visual Logic & Debugging Layer
**Target: Layer 13 (Observability)**

### Benefits for Assest:
- **Visual Ingestion Audit**: We can mirror our 16-layer ingestion pipeline in Langflow to visually inspect how a document moves from `OCR` -> `Classifier` -> `PII Scrubber`.
- **Rapid Prototyping**: Test new reranking weights or HyDE prompts in a drag-and-drop interface before committing them to the production `retriever.py`.

---

## 3. Implementation Strategy: The "Hybrid" Approach

> [!IMPORTANT]
> To maintain the **high-performance** and **custom security** of our current system, we will follow a hybrid model:

| Component | Choice | Rationale |
| :--- | :--- | :--- |
| **Ingestion Pipeline (L1-L15)** | **Custom (FastAPI + Task Queues)** | Maximum control over PII scrubbing, heavy OCR, and batch embedding. |
| **Query Engine (L16)** | **LangGraph** | Complex cycles, multi-agent collaboration, and state persistence. |
| **Observability** | **Langflow / LangSmith** | Deep tracing of agent thoughts and "Why" behind every answer. |

---

## 4. Next Steps
1.  **Install Dependencies**: Add `langgraph`, `langchain-anthropic`, and `langflow` to `requirements.txt`.
2.  **Refactor Query Loop**: Move `backend/api/query.py` logic into a LangGraph `StateGraph`.
3.  **Implement Verifier Node**: Create a specialized agent that uses the `GraphStore` to validate factual claims.
