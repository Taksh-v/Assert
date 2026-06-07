---
adr: 0001
title: Deepen ingestion pipeline with IngestionOrchestrator seam
status: proposed
date: 2026-05-25
authors: ["auto-agent"]
---

## Context

The repository contains multiple ingestion implementations (legacy pipeline, `pipeline_v2`, and a new ConnectorSyncRunner). The ingestion pipeline is central to the system and currently surfaces transformer sequencing, persistence, and error handling across multiple call sites.

## Decision

Introduce a single seam: `IngestionOrchestrator`, a deep interface that encapsulates transformer sequencing, error handling, retry/provenance, and persistence. Provide two adapters that implement this interface:

- `LegacyIngestionOrchestrator` — wraps existing legacy pipeline for backward compatibility.
- `PilotIngestionOrchestrator` — implements the new `ConnectorSyncRunner` semantics and RunLedger lifecycle.

Callers will use the `IngestionOrchestrator` interface (or a factory) instead of invoking pipeline internals directly.

## Consequences

- Localizes orchestration complexity and reduces coupling between callers and transformer internals.
- Simplifies parity testing: contract tests can call the seam and compare outputs without dealing with intermediate elements.
- Enables deterministic adapters (NullSanitizer, DummyQdrant) to be injected for CI and unit tests.
- Requires a small migration: replace direct pipeline calls with the orchestrator in a few call sites.

## Next Steps

1. Add domain types: `SemanticChunk`, `ExtractionContext` to `CONTEXT.md`.
2. Create a lightweight `backend/ingestion/orchestrator.py` implementing the interface and two adapters (stubs).
3. Add unit/contract tests calling the seam directly.
4. Migrate one caller (e.g., `ConnectorSyncRunner`) to use the seam as a pilot.
5. Iterate and extract more invariants behind the seam.
