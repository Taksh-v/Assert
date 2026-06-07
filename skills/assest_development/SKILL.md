---
name: assest_development
description: Development guidelines, architecture blueprints, and common pitfalls for the Assest Company Brain engine.
---

# Assest Development guidelines

This skill contains the core guidelines, architectural mappings, and developer learnings acquired during the construction of the Assest "Company Brain" cognitive engine. Use these rules to ensure production-grade implementation, avoid common pitfalls, and preserve system integrity.

## 1. Architectural Architecture & Data Flow

Assest is structured around a multi-layered ingestion, vector storage, and agentic reasoning workflow:
1. **Ingestion**: Slack, Notion, and Google Drive source documents are normalized, parsed, PII-scrubbed, and classified.
2. **DLQ Routing**: Any document stream failures are isolated within `IngestionPipeline` (using Semaphore concurrency gates) and routed to the `failed_ingestions` table as a Dead Letter Queue (DLQ).
3. **Storage & Retrieval**: Normalized documents are chunked and upserted as multi-vector embeddings to Qdrant (Layer 8) and metadata tables in SQLite (`assest_dev.db`).
4. **Agent Swarm / Reasoning**: Intent classification is performed by a `SupervisorAgent` which delegates queries dynamically (e.g., to the Quick Retriever, a Comparison Agent, or the Reasoning Orchestrator).
5. **Observability**: Execution traces and spans are recorded using OpenTelemetry to local telemetry log files.

---

## 2. Key Pitfalls & Best Practices

### A. DLQ Scheduler & `FailedIngestion` Schema Alignment
* **Issue**: The DLQ model in [failed_ingestion.py](file:///Users/takshvadaliya/Desktop/assert/backend/models/failed_ingestion.py) does not contain a `file_name` column. Attempting to access `record.file_name` triggers an `AttributeError`.
* **Fix/Standard**: Always use `record.source_url` for logging/identifying files in the DLQ loop.
* **Connector Lookup**: `FailedIngestion` records do not contain a direct `connector_id` column. Connectors must be queried dynamically by matching `workspace_id` and the `source_type` string:
  ```python
  stmt_conn = select(Connector).where(Connector.workspace_id == record.workspace_id)
  res_conn = await session.execute(stmt_conn)
  connectors = res_conn.scalars().all()
  connector = next((c for c in connectors if getattr(c.type, "value", c.type) == record.source_type), None)
  ```
* **Selected IDs**: Pass the external resource ID (`source_id`) extracted from `record.raw_payload.get("source_id")` instead of `record.id` as the `selected_ids` filter to `ingestion_pipeline.run()`.

### B. Python Dual-Runtime Path Merging
* **Issue**: macOS environment packages may be split between python3.10 and python3.12 site-packages.
* **Standard**: When executing backend servers or migration commands, always verify that `PYTHONPATH` includes both site-package directories to guarantee imports (e.g. `groq`, `qdrant_client`, `sqlite`) resolve correctly. Refer to [run.sh](file:///Users/takshvadaliya/Desktop/assert/run.sh) for environment detection logic.

### C. Qdrant Local Mode Lockouts
* **Issue**: Local Qdrant client runs in file-storage mode. Running multiple instances of the backend/uvicorn workers simultaneously locks the storage directory, causing client initialization failures.
* **Standard**: Ensure only one backend process is running. Always check port 8000 using `lsof -Pi :8000` before spawning new instances.

---

## 3. Development Workflow

1. **Local Development First**: Connectors default to zero-config mocks in the local sandbox environments to minimize API token costs and rate-limit penalties.
2. **Database Migrations**: Always execute migrations in a safe task queue or verify locks on `assest_dev.db` before applying updates.
3. **No Fluff & No Mocking in Production**: Use production patterns for connectors (rate limits, exception retry bounds, and OAuth credential rotation) by default.
