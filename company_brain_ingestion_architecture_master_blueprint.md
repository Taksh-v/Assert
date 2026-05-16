# Company Brain — Enterprise AI Ingestion & Knowledge Infrastructure Blueprint

---

# 1. Vision

The Company Brain is not just a chatbot or a RAG system.

It is:

```text
A continuously evolving organizational memory system.
```

The goal is to transform fragmented enterprise information into:

- structured knowledge
- semantic memory
- relationship graphs
- retrieval-optimized context
- reasoning-ready intelligence

The ingestion layer is the most critical layer because:

```text
Weak ingestion = weak retrieval = hallucinated responses
Strong ingestion = intelligent enterprise AI
```

---

# 2. Core Philosophy

Traditional RAG systems do this:

```text
Upload File
↓
Chunk
↓
Embed
↓
Store
↓
Chat
```

This architecture fails at scale.

The correct architecture is:

```text
Raw Data
↓
Normalization
↓
Extraction
↓
Structure Reconstruction
↓
Metadata Enrichment
↓
Knowledge Object Creation
↓
Relationship Mapping
↓
Hybrid Indexing
↓
Retrieval Optimization
↓
Reasoning
```

---

# 3. High-Level System Architecture

```text
                    ┌─────────────────────┐
                    │     Connectors      │
                    │ Notion/Slack/GDrive │
                    │ CRM/PDF/API/Github  │
                    └─────────┬───────────┘
                              │
                              ▼
                  ┌──────────────────────┐
                  │ Source Normalization │
                  └─────────┬────────────┘
                            │
                            ▼
                 ┌────────────────────────┐
                 │ Multimodal Extraction  │
                 │ OCR/Tables/Images      │
                 └─────────┬──────────────┘
                           │
                           ▼
               ┌──────────────────────────┐
               │ Structure Reconstruction │
               └─────────┬────────────────┘
                         │
                         ▼
              ┌───────────────────────────┐
              │ Metadata Enrichment       │
              └─────────┬─────────────────┘
                        │
                        ▼
               ┌─────────────────────────┐
               │ Adaptive Chunking       │
               └─────────┬───────────────┘
                         │
                         ▼
              ┌──────────────────────────┐
              │ Knowledge Object Builder │
              └─────────┬────────────────┘
                        │
        ┌───────────────┴────────────────┐
        ▼                                ▼
┌──────────────────┐          ┌──────────────────┐
│ Vector Database  │          │ Relational Store │
│ Semantic Search  │          │ Metadata & ACLs  │
└──────────────────┘          └──────────────────┘
        │                                │
        └───────────────┬────────────────┘
                        ▼
              ┌────────────────────┐
              │ Retrieval Engine   │
              └────────────────────┘
```

---

# 4. Core System Layers

# Layer 1 — Connectors

## Purpose

Connectors ingest data from external systems.

## Supported Sources

### Collaboration
- Notion
- Slack
- Microsoft Teams
- Discord

### Storage
- Google Drive
- Dropbox
- OneDrive
- Amazon S3

### Development
- GitHub
- GitLab
- Jira
- Confluence

### CRM / ERP
- Salesforce
- HubSpot
- SAP

### Communication
- Gmail
- Outlook
- Zoom transcripts

### Custom Sources
- APIs
- Webhooks
- Databases
- CSV uploads

---

## Connector Architecture

Each connector should support:

```text
Authentication
↓
Permission Access
↓
Incremental Sync
↓
Event Listening
↓
Data Extraction
↓
Schema Mapping
```

---

## Important Features

### Incremental Sync

Never reprocess everything.

Track:
- created
- updated
- deleted
- moved
- permission changed

---

## Event-Driven Ingestion

Use:
- webhooks
- CDC (Change Data Capture)
- Kafka events

This enables real-time knowledge updates.

---

# Layer 2 — Source Normalization

Different sources produce inconsistent formats.

Example:

| Source | Format |
|---|---|
| PDF | binary |
| Slack | messages |
| Notion | blocks |
| GitHub | markdown/code |
| Email | threads |
| Image | pixels |

The normalization layer converts all sources into a unified internal schema.

---

## Unified Internal Schema

```json
{
  "source_id": "",
  "workspace_id": "",
  "document_id": "",
  "document_type": "",
  "mime_type": "",
  "raw_content": "",
  "metadata": {},
  "permissions": []
}
```

---

# Layer 3 — Multimodal Extraction

This is where raw files become machine-readable.

## Text Extraction

Used for:
- txt
- md
- docs
- html

Tools:
- Unstructured
- BeautifulSoup
- markdown parsers

---

## PDF Extraction

PDFs are extremely difficult because:
- layouts break
- tables collapse
- headers repeat
- OCR may be required

Use:
- PyMuPDF
- Docling
- LayoutParser
- pdfplumber

---

## OCR Extraction

For:
- scanned PDFs
- screenshots
- images

Use:
- PaddleOCR
- Tesseract
- EasyOCR

---

## Table Extraction

Never flatten tables blindly.

Preserve:
- rows
- columns
- schema
- relationships

Store:
- table embeddings
- summaries
- structured rows

---

## Audio & Video

Process:
- transcription
- speaker diarization
- topic segmentation
- action item extraction

Use:
- Whisper
- pyannote

---

# Layer 4 — Structure Reconstruction

Most systems lose hierarchy.

This destroys retrieval quality.

## Preserve Structure

Example:

```text
Company SOP
 ├── Authentication
 │    ├── JWT
 │    ├── OAuth
 │    └── Sessions
```

Store:
- headings
- nesting
- tables
- references
- links
- citations

---

# Layer 5 — Metadata Enrichment

This layer is critical.

Metadata dramatically improves retrieval precision.

## Metadata Types

### Source Metadata
- source
- file path
- owner
- workspace

### Semantic Metadata
- entities
- topics
- keywords
- summaries

### Security Metadata
- ACLs
- permissions
- visibility

### Temporal Metadata
- created_at
- updated_at
- version

---

## Example Metadata Schema

```json
{
  "title": "Authentication Flow",
  "department": "Engineering",
  "entities": ["JWT", "OAuth"],
  "author": "Backend Team",
  "visibility": "internal"
}
```

---

# Layer 6 — Adaptive Chunking

This is one of the most important layers.

## Bad Chunking

```text
Every 500 tokens
```

This breaks:
- semantic continuity
- tables
- workflows
- code blocks

---

## Correct Chunking

Use:
- heading-aware chunking
- semantic chunking
- layout-aware chunking
- modality-aware chunking

---

## Chunking Strategy

### Text

Chunk by:
- sections
- paragraphs
- semantic boundaries

---

### Code

Chunk by:
- functions
- classes
- modules

---

### Tables

Chunk by:
- row groups
- semantic meaning

---

### Meetings

Chunk by:
- topic transitions
- speakers

---

# Layer 7 — Knowledge Object Builder

DO NOT think in chunks.

Think in:

```text
Knowledge Objects
```

A knowledge object represents:
- a concept
- a workflow
- a process
- a policy
- an incident
- a customer issue

---

## Example

```text
Invoice Approval Workflow
```

Connected to:
- Slack discussion
- Jira ticket
- SOP document
- Zoom meeting
- API logs

---

## Knowledge Object Schema

```json
{
  "object_id": "",
  "type": "workflow",
  "title": "",
  "summary": "",
  "entities": [],
  "relationships": [],
  "source_documents": [],
  "embeddings": []
}
```

---

# Layer 8 — Embedding Layer

Embeddings convert semantic meaning into vectors.

## Best Embedding Models

### Open Source
- BGE-M3
- e5-large
- jina-embeddings
- Qwen embeddings

---

## Important Concepts

### Multi-Vector Embeddings

Store:
- title embedding
- chunk embedding
- summary embedding

---

## Hybrid Embeddings

Store:
- semantic vectors
- sparse vectors (BM25)
- metadata filters

---

# Layer 9 — Storage Layer

Never use only vector databases.

Use hybrid storage.

## Recommended Storage Architecture

| Data Type | Storage |
|---|---|
| Raw Files | S3 / R2 |
| Metadata | PostgreSQL |
| Semantic Search | Qdrant |
| Relationships | Neo4j |
| Cache | Redis |

---

## Why PostgreSQL?

Use for:
- permissions
- lineage
- audit logs
- metadata
- relationships

---

## Why Qdrant?

Best for:
- metadata filtering
- hybrid retrieval
- high performance
- scalability

---

## Why Neo4j?

Used for:
- relationship traversal
- graph reasoning
- multi-hop retrieval

---

# Layer 10 — Knowledge Graph

This layer separates enterprise systems from normal RAG.

## Graph Relationships

```text
Employee → Team
Team → Project
Project → SOP
SOP → Incident
Incident → Meeting
```

---

## Benefits

Enables:
- multi-hop reasoning
- relationship retrieval
- context expansion
- agent memory

---

# Layer 11 — Permissions & Security

Most AI systems fail here.

Every chunk/object must inherit permissions.

## Permission Model

```json
{
  "allowed_users": [],
  "allowed_groups": [],
  "visibility": "private"
}
```

---

## Critical Rule

Permission filtering must happen:

```text
BEFORE retrieval
```

Not after.

---

# Layer 12 — Retrieval Engine

This is where the intelligence emerges.

## Enterprise Retrieval Pipeline

```text
User Query
↓
Query Understanding
↓
Intent Detection
↓
Metadata Extraction
↓
Permission Filtering
↓
Hybrid Search
↓
Graph Expansion
↓
Reranking
↓
Context Compression
↓
LLM
```

---

## Hybrid Retrieval

Never use only vector search.

Use:

```text
BM25 + Dense Retrieval + Metadata Filters + Reranking
```

---

## Reranking

Cross-encoders improve relevance significantly.

Use:
- bge-reranker
- jina reranker

---

# Layer 13 — Observability

This is mandatory in production.

## Metrics

Track:
- ingestion latency
- failed files
- extraction quality
- duplicate rate
- stale embeddings
- retrieval precision
- sync health

---

## Dead Letter Queue

Failed documents should go into:

```text
DLQ (Dead Letter Queue)
```

This enables:
- retries
- debugging
- replayability

---

# Layer 14 — Incremental Sync

Critical for scalability.

## Track Changes

```text
created
updated
deleted
permissions changed
moved
renamed
```

---

## Benefits

Avoid:
- re-embedding everything
- unnecessary compute
- stale retrieval

---

# Layer 15 — Versioning

Knowledge changes over time.

Store:
- document versions
- embedding versions
- chunk versions

---

## Why?

Enables:
- rollback
- auditability
- temporal reasoning

---

# Layer 16 — Agentic Memory Layer

Future-ready architecture.

Agents should remember:
- workflows
- decisions
- conversations
- user preferences
- historical context

## Types of Memory

| Type | Purpose |
|---|---|
| Episodic | events |
| Semantic | facts |
| Procedural | workflows |
| Working | temporary context |

---

# Recommended Technology Stack

| Layer | Technology |
|---|---|
| API | FastAPI |
| Orchestration | Temporal |
| Queue | Kafka |
| Connector Framework | Airbyte |
| Extraction | Unstructured |
| OCR | PaddleOCR |
| Metadata DB | PostgreSQL |
| Vector DB | Qdrant |
| Graph DB | Neo4j |
| Cache | Redis |
| Blob Storage | S3 / R2 |
| Embeddings | BGE-M3 |
| Reranker | bge-reranker |
| Monitoring | Prometheus + Grafana |

---

# Event-Driven Architecture

Use asynchronous pipelines.

## Example

```text
New Slack Message
↓
Webhook Trigger
↓
Kafka Event
↓
Extraction Worker
↓
Chunking Worker
↓
Embedding Worker
↓
Storage Worker
↓
Index Update
```

---

# Scalability Principles

Your ingestion layer must be:

```text
Idempotent
Replayable
Distributed
Versioned
Observable
Incremental
Permission-aware
Schema-flexible
```

---

# Recommended Folder Structure

```text
company-brain/
├── connectors/
├── ingestion/
├── extraction/
├── chunking/
├── embeddings/
├── graph/
├── retrieval/
├── api/
├── orchestration/
├── observability/
├── workers/
├── vector_store/
├── metadata_store/
└── frontend/
```

---

# Suggested Database Design

## PostgreSQL Tables

### documents
- id
- workspace_id
- source
- title
- owner
- created_at
- updated_at

### chunks
- id
- document_id
- chunk_text
- summary
- metadata
- embedding_id

### permissions
- id
- document_id
- user_id
- role

### knowledge_objects
- id
- title
- type
- relationships

---

# Suggested Queue Architecture

## Kafka Topics

```text
connector-events
raw-documents
parsed-documents
chunk-events
embedding-events
retrieval-metrics
failed-events
```

---

# Suggested Worker Architecture

## Workers

### Extraction Worker
Responsible for:
- parsing
- OCR
- cleanup

### Chunking Worker
Responsible for:
- semantic chunking
- hierarchy preservation

### Embedding Worker
Responsible for:
- vector generation
- batch processing

### Storage Worker
Responsible for:
- Qdrant storage
- PostgreSQL updates

### Graph Worker
Responsible for:
- entity relationships
- graph updates

---

# What Makes Enterprise AI Truly Powerful

Not the LLM.

The differentiator is:

```text
Knowledge Infrastructure
```

The companies winning in enterprise AI are winning because:
- ingestion is strong
- metadata is rich
- retrieval is optimized
- permissions are correct
- graph relationships exist

---

# Ultimate Goal

Your Company Brain should evolve into:

```text
A continuously learning organizational operating system.
```

Not just:
- chatbot
- search engine
- vector database

But:
- institutional memory
- reasoning infrastructure
- enterprise cognition layer

---

# Final Recommended Architecture

```text
Connectors
↓
Normalization
↓
Extraction
↓
Structure Reconstruction
↓
Metadata Enrichment
↓
Adaptive Chunking
↓
Knowledge Objects
↓
Embeddings
↓
Hybrid Storage
↓
Graph Relationships
↓
Hybrid Retrieval
↓
Reranking
↓
LLM Reasoning
↓
Agent Memory
```

---

# Final Advice

Focus first on:

1. ingestion quality
2. metadata quality
3. retrieval quality

Everything else becomes easier after that.

Bad ingestion cannot be fixed later with a stronger model.

Strong knowledge infrastructure compounds over time and becomes the moat of the product.

