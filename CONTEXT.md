# Assest Domain Context

## Terms

### Document ingestion run

A single-document Company Brain lifecycle that takes one raw document from a connector and produces the persisted and indexed knowledge artifacts for that document. It owns normalization, parsing, scrubbing, classification, enrichment, entity resolution, chunking, document/chunk persistence, vector indexing, graph writes, and event writes behind one interface.

Connector sync owns fetching documents, concurrency, sync state, stats, and DLQ routing around document ingestion runs.

## New domain terms introduced 2026-05-25

- `IngestionOrchestrator`: seam that orchestrates transformer sequencing, persistence, and provenance for ingestion jobs. Callers should depend on the interface, not pipeline internals.
- `SemanticChunk`: explicit domain type representing a chunk of semantic content with provenance metadata and token/span bounds.
- `ExtractionContext`: domain type carrying extraction-time metadata (source id, run id, offsets, tokenizer state) used by extractors and storage adapters.

