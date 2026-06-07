Title: Ingestion Seams and Contracts
Date: 2026-05-23
Status: Accepted

Context
-------
We need a maintainable and testable ingestion pipeline that separates concerns between document persistence, indexing, and orchestration.

Decision
--------
Introduce three primary seams:

- `DocumentStore` — a persistence adapter responsible for document records and chunks. Implementations: `SQLDocumentStore`.
- `IndexAdapter` — an adapter for vector/graph stores. Implementations: `DefaultIndexAdapter` (qdrant, neo4j wrappers) and test/noop implementations.
- `IngestionRunner` — the orchestrator that selects templates, runs transformers, and coordinates persistence and indexing.

Agents and tests interact with these seams via small runtime protocols declared in `backend/agents/contracts.py`.

Consequences
------------
- Easier unit/integration testing using no-op/mock stores.
- Safer async behavior: blocking index operations are wrapped in async helpers, and ingestion has per-document timeouts and lightweight timing.

Signed-off-by: Development Team
