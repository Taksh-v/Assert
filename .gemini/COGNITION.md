# 🧠 Gemini CLI Cognitive Operating System
## Project: Assest Company Brain

---

# 1. Architectural Mandates (The "Ground Truth")
- **Core Stack:** Zero-cost, local-first. (LiteLLM Gateway → Ollama/vLLM).
- **Environment:** System Python Only (No venv).
- **Primary LLM Hub:** All AI calls *must* flow through `backend.core.llm_client.LLMClient`.
- **Database Logic:** Use `aiosqlite` for async local development. PostgreSQL for production.
- **Security:** Presidio PII scrubbing is mandatory in the ingestion pipeline.

---

# 2. Procedural Knowledge (Learned Fixes)
- **LiteLLM Stability:** Always clear `litellm.success_callback` and `litellm.failure_callback` in `__init__` to prevent Langfuse version mismatch crashes.
- **Database Constraints:** The `documents` table `connector_id` field must be `nullable=True` to support manual uploads and test payloads.
- **Model Naming:** Use `openai/` prefix for routed models (e.g., `openai/company-brain-fast`) to satisfy LiteLLM provider requirements.

---

# 3. Multi-Agentic Protocols (The Swarm)
When executing tasks, I shift between these specialized personas:
- **[PLANNER]:** Decomposes complex user goals into sequential steps.
- **[ARCHITECT]:** Ensures new code follows the 18-layer master blueprint.
- **[CODER]:** Writes surgical, production-grade implementations.
- **[VERIFIER]:** Specifically creates and runs verification scripts for every change.

---

# 4. Context Engineering Rules
- **Hierarchical Authority:** `PROGRESS.md` is the source of truth for task status.
- **Rolling Summaries:** Long tool-chains must be summarized and the detailed logs pruned from active reasoning.
- **Dependency First:** Read module imports and downstream dependencies before modifying any logic.

---

# 5. Advanced Reasoning Layers
- **Temporal:** recency-aware ranking (30-day boost) is enabled.
- **Analytical:** Route "How many/Count" queries to `WrenAITool` (Port 5566).
- **Memory:** Use incremental episode summarization for amnesia-free chat.
