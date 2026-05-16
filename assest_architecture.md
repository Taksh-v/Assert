# Assest — Architecture Deep Dive
### The Complete System Brain: How It Thinks, Why It Works, and How to Build It
**For Antigravity AI IDE — Read This Before Writing Any Code**

---

> **How to use this document**
> This file explains the architecture of Assest at the deepest level — not just what to build, but why each decision was made. Every section contains: the concept (what it is), the reasoning (why it exists), and the implementation spec (how to build it). Paste the relevant section into Antigravity before each coding task. The reasoning sections are not commentary — they are requirements. An implementation that ignores the reasoning will produce a system that works technically but fails in production.

---

## Table of Contents

1. [System Philosophy — The Mental Model](#1-system-philosophy--the-mental-model)
2. [How LLMs Work — What Antigravity Must Understand](#2-how-llms-work--what-antigravity-must-understand)
3. [The Knowledge Pipeline — How Information Moves](#3-the-knowledge-pipeline--how-information-moves)
4. [Ingestion Layer — How Raw Data Becomes Knowledge](#4-ingestion-layer--how-raw-data-becomes-knowledge)
5. [Chunking Strategy — The Most Underrated Decision](#5-chunking-strategy--the-most-underrated-decision)
6. [Embeddings — How Meaning Becomes Math](#6-embeddings--how-meaning-becomes-math)
7. [The Vector Database — How Knowledge Is Stored](#7-the-vector-database--how-knowledge-is-stored)
8. [Hybrid Retrieval — How the Right Knowledge Is Found](#8-hybrid-retrieval--how-the-right-knowledge-is-found)
9. [Ranking System — How Results Are Prioritised](#9-ranking-system--how-results-are-prioritised)
10. [Context Engineering — How Knowledge Reaches the LLM](#10-context-engineering--how-knowledge-reaches-the-llm)
11. [Memory Architecture — How the System Remembers](#11-memory-architecture--how-the-system-remembers)
12. [The Knowledge Graph — How Relationships Are Understood](#12-the-knowledge-graph--how-relationships-are-understood)
13. [AI Agent Orchestration — How Agents Work Together](#13-ai-agent-orchestration--how-agents-work-together)
14. [Skills File System — How Knowledge Becomes Action](#14-skills-file-system--how-knowledge-becomes-action)
15. [Metadata Design — The Hidden Layer That Makes Everything Work](#15-metadata-design--the-hidden-layer-that-makes-everything-work)
16. [Database Architecture — Where Everything Lives](#16-database-architecture--where-everything-lives)
17. [Data Flow Diagrams — The Complete Picture](#17-data-flow-diagrams--the-complete-picture)
18. [Failure Modes — What Goes Wrong and Why](#18-failure-modes--what-goes-wrong-and-why)
19. [Scaling Strategy — How the System Grows](#19-scaling-strategy--how-the-system-grows)
20. [Antigravity Prompting Patterns for This Architecture](#20-antigravity-prompting-patterns-for-this-architecture)

---

## 1. System Philosophy — The Mental Model

### The Core Idea

Most knowledge management systems are built around a simple metaphor: a library. You store documents. You search them. You retrieve them.

Assest is built around a different metaphor: **a brain**.

A brain does not just store and retrieve. It understands relationships. It compresses redundant information. It prioritises what matters. It forgets what is stale. It connects things that were never explicitly connected. It learns from how questions are asked and answered. It knows the difference between a fact and a decision and a process.

This distinction is not philosophical — it has direct technical consequences for every decision in the system.

### The Five Properties of a Company Brain

Every architectural decision in Assest must serve these five properties:

**Property 1 — Grounded**
The system never generates information. It only retrieves, structures, and presents information that already exists in the company's own sources. Hallucination is not a risk to manage — it is a property to eliminate by design. Every answer must be traceable to a source document.

**Property 2 — Current**
Knowledge that is stale is worse than no knowledge. A wrong answer delivered confidently causes real business damage. The system must know when information was last verified, detect when it has likely changed, and flag or remove it accordingly.

**Property 3 — Structured**
Raw text is not useful to AI agents. A paragraph describing the refund policy is useful to a human. A structured decision tree is useful to an agent. The system must progressively structure knowledge — from raw text to chunks to structured skills — as it matures.

**Property 4 — Permissioned**
Not all knowledge should be available to all agents or all employees. The system must enforce access control at the knowledge level, not just the UI level. A customer support agent should not have access to salary information even if both live in the same Notion workspace.

**Property 5 — Explainable**
When the system gives an answer, it must be able to show exactly where that answer came from, how confident it is, and what it does not know. This is not a nice-to-have — it is what makes the system trustworthy enough to actually change how people work.

### The Hierarchy of Knowledge

Not all information is equal. Assest must understand this hierarchy:

```
TIER 1 — CANONICAL KNOWLEDGE
Deliberately written to be authoritative.
Examples: SOPs, policy documents, runbooks, architecture decision records.
Characteristics: High trust, low frequency of change, high signal.
Treatment: Ingest always, high retrieval weight, slow staleness timer.

TIER 2 — DERIVED KNOWLEDGE
Created as a byproduct of work, but contains real knowledge.
Examples: Closed support tickets (how issues were solved), merged PRs
(engineering decisions), resolved incidents (what went wrong and why).
Characteristics: Medium trust, medium frequency, moderate signal.
Treatment: Ingest selectively, medium retrieval weight, medium staleness timer.

TIER 3 — CONVERSATIONAL KNOWLEDGE
Emerges from communication, mostly noise with occasional signal.
Examples: Slack threads, email chains, meeting notes.
Characteristics: Low trust (informal), high frequency, low signal.
Treatment: Ingest only high-signal signals (pinned, long threads,
reaction-heavy), low retrieval weight, fast staleness timer.

TIER 4 — IMPLICIT KNOWLEDGE
Never written down. Lives in people's heads.
Examples: Why a decision was made, what not to do, how to read a client.
Characteristics: Highest value, not yet ingested.
Treatment: Surface through question patterns. When a question is asked
repeatedly and not answered well — that is implicit knowledge that
needs to be captured.
```

**Why this matters for code:** Every ingested document must be tagged with its tier. Retrieval queries must be weighted by tier. Staleness timers must vary by tier. The tier is a metadata field on every chunk.

---

## 2. How LLMs Work — What Antigravity Must Understand

### Why This Section Exists

Antigravity writes code that interacts with LLMs. If it does not understand how LLMs work, it will write code that technically runs but produces poor results. This section gives the mental model required to prompt LLMs correctly inside the Assest system.

### The Core Mechanic: Prediction

An LLM does not think. It predicts. Given a sequence of tokens (text broken into pieces), it predicts the most likely next token, then the next, then the next, building an answer one token at a time.

This has a critical implication: **the quality of the output is entirely determined by the quality of the input**. The LLM has no way to go get more information. It works only with what is in its context window.

This is why the retrieval system matters so much. We are responsible for putting the right information in front of the LLM. If we retrieve the wrong chunks, the LLM will produce a wrong answer — not because it is broken, but because we gave it the wrong material.

### The Context Window

Every LLM has a context window — the maximum amount of text it can process at once. Claude claude-sonnet-4-20250514 has a 200,000 token context window. One token is approximately 0.75 words.

Implications for Assest:
- We can technically fit enormous amounts of retrieved text in one call
- But more text does not mean better answers — it means the LLM must work harder to find the relevant part
- Optimal context: retrieve 5-8 highly relevant chunks, not 50 loosely relevant ones
- The signal-to-noise ratio of the context window directly determines answer quality

### Temperature and Determinism

Temperature controls how creative vs deterministic the LLM's predictions are.

- Temperature 0: Always picks the most likely next token. Fully deterministic. Same input always produces same output. Use for: factual Q&A, structured extraction, classification.
- Temperature 0.7: Introduces variation. Different runs produce different outputs. Use for: creative writing, brainstorming, drafting.
- Temperature 1.0+: High variation, sometimes incoherent.

**For Assest:** All query answering uses temperature 0. We want deterministic, factual answers. Skills file extraction uses temperature 0. Only content that requires creativity (email drafting, summaries) uses temperature 0.3-0.5.

### System Prompts vs User Prompts

Every call to Claude has two key parts:

**System prompt:** Sets the behaviour, role, and constraints of the model. This is where we tell Claude: "You are the Assest knowledge assistant. You only answer based on provided context. Never hallucinate." The system prompt is permanent for the duration of the conversation.

**User prompt:** The actual question or task, including retrieved context. This changes with every query.

**For Assest:** The system prompt is not optional boilerplate. It is a critical control mechanism. It must explicitly state:
- What the model is allowed to do
- What the model is not allowed to do (generate information not in context)
- How to format the response
- How to handle cases where the answer is not in the context
- How to cite sources

### Why Claude Over Other Models for Assest

Claude (Anthropic) is chosen for Assest for specific technical reasons:

1. **Instruction following:** Claude follows complex, multi-part system prompt instructions more reliably than most alternatives. This matters enormously when telling it "never answer outside the provided context."

2. **Citation accuracy:** Claude is less likely to misattribute sources when asked to cite. For a knowledge base product, wrong citations destroy trust.

3. **Long context handling:** Claude's 200K context window and its ability to attend to information throughout that window (not just the beginning and end) means better retrieval of relevant chunks even in large context calls.

4. **Refusal consistency:** Claude is more consistent about saying "I don't know" when the answer is not in the context, rather than hallucinating a plausible-sounding answer.

---

## 3. The Knowledge Pipeline — How Information Moves

### The Complete Journey of a Document

Understanding this end-to-end flow is essential before building any individual component. Every component is designed in service of this journey.

```
SOURCE (Notion page, Google Doc, Slack thread)
    │
    ▼
FETCH (Connector pulls raw content via API)
    │
    ▼
PARSE (Unstructured.io extracts clean text from any format)
    │
    ▼
CLASSIFY (What tier is this? What type of content?)
    │
    ▼
PII SCRUB (Remove personal data before storage)
    │
    ▼
CHUNK (Split into semantically meaningful pieces)
    │
    ▼
ENRICH (Add metadata: tier, type, relationships, timestamps)
    │
    ▼
EMBED (Convert text to vectors using embedding model)
    │
    ▼
DEDUPLICATE (Hash check — has this content been stored before?)
    │
    ▼
STORE (Vectors in Qdrant, metadata in PostgreSQL, raw in S3)
    │
    ▼
INDEX (Update search indexes for keyword retrieval)
    │
    ▼
GRAPH (Extract entities and relationships for knowledge graph)
    │
    ▼
SKILLS CHECK (Does this content contribute to a skills file?)
    │
    ▼
FRESHNESS TIMER SET (When should this be re-evaluated?)
    │
    ▼
AUDIT LOG (Record that this document was ingested, by whom, when)
```

### Why Each Stage Cannot Be Skipped

**CLASSIFY before CHUNK:** If you do not know what type of document you are chunking, you will chunk it wrong. A policy document should be chunked by section. A support ticket should be chunked as a complete unit. A long engineering doc should be chunked by concept boundary.

**PII SCRUB before EMBED:** If you embed text containing PII and store it in the vector database, you cannot easily remove it later. The PII is now encoded in 1536-dimensional space. You would need to re-embed the entire document after scrubbing. Always scrub first.

**DEDUPLICATE after EMBED but before STORE:** You need the embedding to do semantic deduplication (is this the same content even if worded differently?). But you do not want to store duplicates. The deduplication gate sits between embedding and storage.

**GRAPH after STORE:** The knowledge graph enriches what is already stored. It adds relationship edges between existing entities. This runs asynchronously — it does not block the ingestion pipeline.

**FRESHNESS TIMER as final step:** Only after everything is confirmed stored do you set the timer. If the timer is set before storage completes and the job crashes, you will think the content is fresh when it was never stored.

---

## 4. Ingestion Layer — How Raw Data Becomes Knowledge

### The Connector Pattern

Every data source connector in Assest follows the same abstract pattern. This is not stylistic consistency — it is what allows the system to add new connectors (WhatsApp, Jira, Linear) without changing the ingestion pipeline.

```python
# CONCEPT FOR ANTIGRAVITY:
# Every connector must implement exactly these four methods.
# The ingestion pipeline only calls these four methods.
# The connector is responsible for all source-specific complexity.
# The pipeline is responsible for all source-agnostic processing.

class BaseConnector:
    
    def validate_config(self, config: dict) -> ValidationResult:
        """
        WHY: Before attempting to connect, verify the credentials are
        structurally valid. Do not make API calls here. Just check that
        required fields exist and are formatted correctly.
        This prevents confusing errors deep in the pipeline.
        """
        raise NotImplementedError
    
    def connect(self, config: dict) -> ConnectionResult:
        """
        WHY: Establish and verify the connection. Make a cheap test API
        call to confirm credentials work. Return a connection object that
        subsequent methods use. This separates auth errors from data errors.
        """
        raise NotImplementedError
    
    def fetch_documents(self, connection, since: datetime = None) -> Iterator[RawDocument]:
        """
        WHY: Returns an iterator (not a list) because some sources have
        thousands of documents. Loading all into memory before processing
        causes crashes. The pipeline processes one document at a time.
        The 'since' parameter enables incremental sync — only fetch what
        changed since the last sync. This is critical for performance.
        """
        raise NotImplementedError
    
    def get_sync_metadata(self, connection) -> SyncMetadata:
        """
        WHY: Returns information about what is available to sync:
        total document count, last modified timestamps, available scopes.
        Used by the admin dashboard to show sync status without triggering
        a full sync.
        """
        raise NotImplementedError
```

### Incremental vs Full Sync

**Full sync:** Fetch every document from the source. Compare with what is stored. Process everything that is new or changed. This is expensive and should only run on first setup or manual request.

**Incremental sync:** Fetch only documents modified since the last sync timestamp. This is what runs on the schedule (every 6 hours for Notion, every hour for Slack). Critical for performance.

**Why this matters:** A Notion workspace with 500 pages should not re-process all 500 pages every hour. It should check which pages were modified in the last hour and process only those. Without incremental sync, the system becomes too expensive to run at scale.

**Implementation requirement:** Every connector must store a `last_sync_cursor` — the timestamp or pagination token that marks where the last successful sync ended. If a sync crashes halfway through, the next run starts from the cursor, not from the beginning.

### The RawDocument Standard

Every connector, regardless of source, must return documents in this standard format. This is the contract between the connector layer and the ingestion pipeline.

```python
class RawDocument:
    # Identity
    source_id: str          # ID in the source system (e.g., Notion page ID)
    source_type: str        # 'notion' | 'google_drive' | 'slack' | 'github'
    workspace_id: str       # Assest workspace this belongs to
    connector_id: str       # Which connector fetched this
    
    # Content
    title: str              # Document title or best available label
    raw_content: str        # Full text, unprocessed
    content_format: str     # 'markdown' | 'plain_text' | 'html'
    
    # Source metadata
    source_url: str         # Direct link back to the source
    author_id: str          # Anonymised author identifier
    created_at: datetime    # When created in source system
    modified_at: datetime   # When last modified in source system
    
    # Assest metadata
    content_hash: str       # SHA256 of raw_content — for deduplication
    fetched_at: datetime    # When Assest fetched this
    
    # Classification hints (connector may know these)
    content_tier: int       # 1, 2, or 3 — connector can guess, pipeline confirms
    content_type: str       # 'policy' | 'runbook' | 'decision' | 'conversation'
    parent_id: str          # For hierarchical sources (Notion sub-pages)
    tags: list[str]         # Source-level tags if available
```

---

## 5. Chunking Strategy — The Most Underrated Decision

### Why Chunking Is Critical

Chunking is the single decision that most affects retrieval quality. Yet most systems treat it as an afterthought — "just split every 500 characters."

Here is why that fails:

Imagine a policy document that says:
> "Refunds are processed within 5 business days. This applies to all orders placed after January 2024. For orders before that date, the old policy applies — contact support."

If you split this naively at a character boundary, you might get:
- Chunk 1: "Refunds are processed within 5 business days. This applies to all orders placed"
- Chunk 2: "after January 2024. For orders before that date, the old policy applies — contact support."

A question about the refund timeline retrieves Chunk 1, which says "5 business days" — but misses the critical date qualifier in Chunk 2. The answer is incomplete and potentially wrong.

Good chunking preserves semantic units — complete thoughts, complete conditions, complete procedures.

### The Chunking Strategy by Content Type

**Policy Documents and SOPs (Tier 1)**
```
Strategy: Section-based chunking
Method: Split on heading boundaries (H1, H2, H3)
         Each section becomes one chunk
         If section > 800 tokens, split at paragraph boundary
Overlap: 100 tokens from previous section's final paragraph
         (preserves "except as noted above" type references)
Minimum chunk size: 50 tokens (discard smaller — not enough context)
Maximum chunk size: 800 tokens

WHY: Policy documents are structured deliberately. The author used
headings to separate concepts. Respecting that structure means each
chunk is a complete thought. An 800 token maximum ensures the LLM
can attend to the full chunk without losing detail.
```

**Support Tickets and Resolved Issues (Tier 2)**
```
Strategy: Conversation-unit chunking
Method: Keep the entire ticket as one chunk:
         [Problem description] + [Resolution steps] + [Outcome]
         Never split a ticket across multiple chunks
If ticket > 1000 tokens: summarise with LLM first, then store summary
Metadata: tag with issue_type, resolution_type, product_area

WHY: A support ticket only has value as a complete unit. The problem
and the resolution must stay together. Retrieving just the problem
without the resolution is useless. Retrieving just the resolution
without the problem lacks context for the agent to know if it applies.
```

**Slack Threads (Tier 3)**
```
Strategy: Thread-unit chunking
Method: Keep the complete thread (question + all replies) as one chunk
         Format: "[Date][Channel] Q: [question] A: [best reply]"
         If thread > 600 tokens: extract only question and highest-reaction reply
Filter: Only threads with 3+ replies OR the question has 2+ reactions

WHY: Individual Slack messages have almost no value alone. The value is
in the exchange — the question that was asked and how it was resolved.
Keeping threads together preserves this exchange unit.
```

**Technical Documentation and READMEs (Tier 1-2)**
```
Strategy: Concept-boundary chunking
Method: Split at natural concept shifts, detected by:
         1. Heading boundaries (primary)
         2. Significant topic change (secondary — use LLM classification)
         Keep code examples WITH their explanatory text
         Never split a code block
Overlap: 150 tokens — technical docs have many forward/back references

WHY: Technical docs frequently reference concepts explained elsewhere.
Higher overlap reduces the chance of a chunk being meaningless without
its surrounding context. Code blocks must never be split — a partial
code example is actively harmful (the agent might try to use broken code).
```

### The Chunk Object — Complete Specification

```python
class Chunk:
    # Identity
    chunk_id: str           # UUID — primary key in Qdrant
    document_id: str        # Parent document ID
    workspace_id: str       # Required for multi-tenant isolation
    
    # Content
    content: str            # Scrubbed, processed text — what gets embedded
    content_tokens: int     # Token count (using tiktoken cl100k_base)
    chunk_index: int        # Position in parent document (0-indexed)
    total_chunks: int       # Total chunks in parent document
    
    # Provenance (where this came from)
    source_url: str         # Direct link to source document
    source_type: str        # 'notion' | 'google_drive' | etc.
    document_title: str     # Title of parent document
    section_heading: str    # Nearest heading above this chunk
    
    # Classification
    content_tier: int       # 1, 2, or 3
    content_type: str       # 'policy' | 'runbook' | 'ticket' | 'thread' | 'doc'
    
    # Temporal
    source_created_at: datetime     # When source was created
    source_modified_at: datetime    # When source was last modified
    ingested_at: datetime           # When Assest processed this
    expires_at: datetime            # When this chunk should be re-evaluated
    
    # Quality signals
    retrieval_count: int    # How many times this chunk was retrieved
    positive_feedback: int  # Times answer using this chunk got thumbs up
    negative_feedback: int  # Times answer using this chunk got thumbs down
    quality_score: float    # Computed: 0.0 to 1.0
    
    # Relationships
    parent_chunk_id: str    # For hierarchical chunking (section → sub-section)
    related_chunk_ids: list[str]  # Semantically related chunks (computed)
    
    # Vector (stored in Qdrant payload, not here)
    # embedding: list[float]  — 1536 dimensions, lives in Qdrant
```

---

## 6. Embeddings — How Meaning Becomes Math

### The Concept

An embedding is a list of numbers — a vector — that represents the meaning of text. The critical property is: **texts with similar meanings produce vectors that are mathematically close to each other**.

This is not magic. It is the result of training a model on vast amounts of text until it learns that "refund" and "reimbursement" appear in similar contexts and should therefore be represented by similar vectors.

For Assest, this means: when a user asks "how do I get my money back?", the embedding of that question will be mathematically close to the embedding of "customer refund policy" — even though the words are completely different. The system finds relevant knowledge by finding chunks whose embeddings are close to the question's embedding.

### The Embedding Model Choice

**Model: text-embedding-3-small (OpenAI)**
- Dimensions: 1536
- Max input tokens: 8191
- Cost: approximately ₹1 per 1 million tokens
- Quality: excellent for English, good for other languages

**Why this model over alternatives:**
- Cheaper than text-embedding-3-large (same quality for most use cases)
- Better multilingual performance than ada-002 (important for India)
- Widely supported by vector database clients including Qdrant
- Consistent API — embeddings from 6 months ago are compatible with today's embeddings (important: do not change embedding models mid-deployment without re-embedding everything)

**Critical rule:** You must use the same embedding model for both documents and queries. If documents are embedded with text-embedding-3-small and the query is embedded with a different model, the vectors will not be comparable and search will fail silently — returning wrong results without any error.

### Embedding at Scale — Batch Processing

A 500-page Notion workspace with average 3 chunks per page = 1500 chunks to embed on initial ingestion.

Naive approach: embed one chunk at a time = 1500 API calls = slow and expensive.

Correct approach: batch embedding.

```python
# CONCEPT FOR ANTIGRAVITY:
# OpenAI embeddings API accepts up to 2048 inputs per call.
# For Assest, use batches of 100 chunks.
# 1500 chunks / 100 per batch = 15 API calls instead of 1500.
# This is ~100x faster and costs the same.

# Pseudocode for the embedder:
def embed_chunks_batch(chunks: list[Chunk]) -> list[Chunk]:
    BATCH_SIZE = 100
    batches = [chunks[i:i+BATCH_SIZE] for i in range(0, len(chunks), BATCH_SIZE)]
    
    for batch in batches:
        texts = [chunk.content for chunk in batch]
        response = openai.embeddings.create(
            model="text-embedding-3-small",
            input=texts
        )
        for chunk, embedding_data in zip(batch, response.data):
            chunk.embedding = embedding_data.embedding
    
    return chunks
```

### Embedding Caching — Do Not Re-Embed Unchanged Content

If a document's content hash has not changed since the last ingestion, the embedding is still valid. Do not re-embed it.

```python
# CONCEPT FOR ANTIGRAVITY:
# Before embedding, check the content_hash against stored chunks.
# If hash matches: skip embedding, update only the ingested_at timestamp.
# If hash differs: delete old chunks, embed new chunks, store.
# If document is new: embed and store.

# This alone reduces embedding API costs by 80%+ for ongoing syncs
# because most documents do not change between syncs.
```

---

## 7. The Vector Database — How Knowledge Is Stored

### Why a Separate Vector Database

PostgreSQL can store vectors (using pgvector extension). Why use Qdrant separately?

Because vector similarity search is a fundamentally different operation from relational queries. When you search a vector database, you are computing the mathematical distance between your query vector and every stored vector, then returning the closest ones. This requires specialised indexing (HNSW — Hierarchical Navigable Small World graphs) that PostgreSQL's pgvector implements poorly at scale.

At 100,000 chunks (a mid-size deployment), pgvector searches become slow. Qdrant, purpose-built for this, maintains sub-millisecond search times at millions of vectors.

**Decision: Qdrant for vectors, PostgreSQL for everything else.**

### Qdrant Collection Design

```python
# CONCEPT FOR ANTIGRAVITY:
# Qdrant organises data into "collections" — equivalent to tables.
# Each collection has vectors of a fixed size (1536 for our embedding model)
# and a distance metric (Cosine for text similarity).
#
# We use ONE collection for all workspaces in MVP.
# Multi-tenant isolation is achieved through metadata filtering.
# workspace_id is a required filter on every single query.
# This is non-negotiable — without it, one customer sees another's data.

collection_config = {
    "name": "assest_knowledge",
    "vectors": {
        "size": 1536,           # Must match embedding model dimensions
        "distance": "Cosine"    # Best for text similarity
    }
}

# Every point (stored chunk) in Qdrant has:
# - id: the chunk_id (UUID)
# - vector: the 1536-dimension embedding
# - payload: all the chunk metadata (everything in the Chunk object except content)
#   NOTE: content is stored in payload too — needed for context assembly
```

### Qdrant Payload Design — What Gets Stored With Each Vector

```json
{
    "chunk_id": "uuid-here",
    "workspace_id": "ws_abc123",
    "document_id": "doc_xyz789",
    "connector_id": "conn_def456",
    
    "content": "Refunds are processed within 5 business days...",
    "content_tokens": 127,
    "content_tier": 1,
    "content_type": "policy",
    
    "source_url": "https://notion.so/page/xyz",
    "source_type": "notion",
    "document_title": "Customer Support Handbook",
    "section_heading": "Refund Policy",
    
    "chunk_index": 3,
    "total_chunks": 12,
    
    "source_modified_at": "2024-01-15T10:30:00Z",
    "ingested_at": "2024-01-16T08:00:00Z",
    "expires_at": "2024-04-16T08:00:00Z",
    
    "quality_score": 0.85,
    "retrieval_count": 47,
    "positive_feedback": 39,
    "negative_feedback": 3
}
```

### Qdrant Indexing — Making Filters Fast

Without indexing, filtering by `workspace_id` requires scanning every vector. With thousands of chunks, this becomes slow.

```python
# CONCEPT FOR ANTIGRAVITY:
# Create payload indexes on fields that will be filtered frequently.
# Do this when creating the collection, before ingesting any data.

indexes_to_create = [
    {"field_name": "workspace_id", "field_schema": "keyword"},
    {"field_name": "content_tier", "field_schema": "integer"},
    {"field_name": "content_type", "field_schema": "keyword"},
    {"field_name": "source_type", "field_schema": "keyword"},
    {"field_name": "source_modified_at", "field_schema": "datetime"},
    {"field_name": "quality_score", "field_schema": "float"}
]

# workspace_id index is the most critical — it is on every single query.
# Without it, query performance degrades linearly with chunk count.
```

---

## 8. Hybrid Retrieval — How the Right Knowledge Is Found

### Why Pure Vector Search Is Not Enough

Vector search finds semantically similar content. But it has a critical weakness: **it is bad at exact matching**.

If a user asks "what is our policy on ISO 27001 certification?", vector search will find chunks about security certifications, compliance, standards, documentation — all semantically related. But if the exact phrase "ISO 27001" only appears in one document and that document uses slightly different wording, vector search might rank it lower than vaguer but more verbose security documents.

Keyword search (BM25) finds exact term matches. But it has the opposite weakness: it misses semantic relationships. "How do I get a refund?" will not find "reimbursement process" via keyword search.

**Hybrid retrieval combines both.** The result is a system that finds the right content whether the user uses exact terminology or describes the concept in their own words.

### The Hybrid Retrieval Architecture

```
USER QUESTION
     │
     ├──────────────────────┬──────────────────────┐
     │                      │                      │
     ▼                      ▼                      ▼
EMBED QUERY          EXTRACT KEYWORDS         EXTRACT FILTERS
(text-embedding      (important terms         (date ranges,
 -3-small)           from question)           source types,
     │                      │                 content tiers)
     ▼                      ▼                      │
QDRANT VECTOR        POSTGRESQL                    │
SEARCH               FULL-TEXT                     │
(top 15 results)     SEARCH (BM25)                 │
(filter: workspace)  (top 15 results)              │
     │               (filter: workspace)            │
     └──────────┬────────────┘                      │
                ▼                                   │
        COMBINE + DEDUPLICATE                       │
        (union of both result sets)                 │
                ▼                                   │
        APPLY METADATA FILTERS ◄───────────────────┘
        (tier, type, date, source)
                ▼
        RERANK (top 8 from combined pool)
                ▼
        CONTEXT ASSEMBLY
                ▼
        CLAUDE API
```

### Implementing BM25 in PostgreSQL

PostgreSQL has native full-text search using tsvector and tsquery. This is your BM25 implementation — no additional service needed.

```sql
-- CONCEPT FOR ANTIGRAVITY:
-- Every chunk record in PostgreSQL needs a search vector column.
-- This column is automatically updated when content changes.

-- Add to chunks table:
ALTER TABLE chunks ADD COLUMN search_vector tsvector;
CREATE INDEX idx_chunks_search ON chunks USING GIN(search_vector);

-- Trigger to auto-update search_vector when content changes:
CREATE FUNCTION update_chunk_search_vector() RETURNS trigger AS $$
BEGIN
    NEW.search_vector := 
        setweight(to_tsvector('english', COALESCE(NEW.document_title, '')), 'A') ||
        setweight(to_tsvector('english', COALESCE(NEW.section_heading, '')), 'B') ||
        setweight(to_tsvector('english', COALESCE(NEW.content, '')), 'C');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- WHY the weights: A (highest) for title, B for heading, C for content.
-- A match in the document title is more significant than a match
-- deep in the body text. BM25 weights reflect this.
```

### Combining Vector and Keyword Results — Reciprocal Rank Fusion

When you have two ranked lists of results (one from vector search, one from keyword search), how do you combine them into one list?

**Reciprocal Rank Fusion (RRF)** is the standard approach:

```python
# CONCEPT FOR ANTIGRAVITY:
# For each result, its RRF score = 1 / (rank + k) where k=60 (standard constant)
# Sum the RRF scores for each chunk across both lists.
# Sort by combined RRF score.
# This is better than averaging similarity scores because
# scores from different systems are not directly comparable.

def reciprocal_rank_fusion(
    vector_results: list[SearchResult],   # ranked by similarity score
    keyword_results: list[SearchResult],  # ranked by BM25 score
    k: int = 60
) -> list[SearchResult]:
    
    scores = {}  # chunk_id -> combined RRF score
    
    for rank, result in enumerate(vector_results):
        scores[result.chunk_id] = scores.get(result.chunk_id, 0) + 1 / (rank + k)
    
    for rank, result in enumerate(keyword_results):
        scores[result.chunk_id] = scores.get(result.chunk_id, 0) + 1 / (rank + k)
    
    # Get all unique chunks
    all_chunks = {r.chunk_id: r for r in vector_results + keyword_results}
    
    # Sort by combined score
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    
    return [all_chunks[chunk_id] for chunk_id, _ in ranked]
```

---

## 9. Ranking System — How Results Are Prioritised

### Why Retrieval Is Not Enough

After hybrid retrieval, you have 15-30 candidate chunks. You need to reduce this to 5-8 chunks to send to Claude. Sending all 30 would:
- Exceed optimal context size
- Dilute the signal with noise
- Increase latency and cost

The ranking system scores each candidate on multiple dimensions and selects the best.

### The Multi-Signal Ranking Formula

```python
# CONCEPT FOR ANTIGRAVITY:
# Each retrieved chunk gets a composite rank score.
# The score combines multiple signals, each weighted.

def compute_rank_score(chunk, query_context) -> float:
    
    # Signal 1: Semantic similarity (from vector search)
    # Weight: 0.35 — most important, but not everything
    semantic_score = chunk.vector_similarity_score * 0.35
    
    # Signal 2: Keyword match strength (from BM25)
    # Weight: 0.20
    keyword_score = chunk.bm25_score * 0.20
    
    # Signal 3: Content tier (Tier 1 > Tier 2 > Tier 3)
    # Weight: 0.20 — a policy document should outrank a Slack message
    tier_map = {1: 1.0, 2: 0.6, 3: 0.3}
    tier_score = tier_map[chunk.content_tier] * 0.20
    
    # Signal 4: Recency (newer content is more likely to be current)
    # Weight: 0.15
    days_old = (datetime.now() - chunk.source_modified_at).days
    recency_score = max(0, 1 - (days_old / 365)) * 0.15
    # Document modified today = 1.0, one year ago = 0.0
    
    # Signal 5: Historical quality (chunks that got good feedback rank higher)
    # Weight: 0.10
    if chunk.retrieval_count > 5:
        total_feedback = chunk.positive_feedback + chunk.negative_feedback
        if total_feedback > 0:
            quality = chunk.positive_feedback / total_feedback
        else:
            quality = 0.5  # neutral default
    else:
        quality = 0.5  # not enough data
    quality_score = quality * 0.10
    
    return semantic_score + keyword_score + tier_score + recency_score + quality_score

# WHY these weights:
# Semantic similarity is most important — it determines relevance.
# Tier matters because authoritative sources should outrank casual ones.
# Recency matters because old policies may be superseded.
# Quality matters because the system learns from feedback over time.
# Keyword match matters for exact-term queries.
```

### Diversity Enforcement — Avoiding Redundant Results

After ranking, you might have the top 5 results all being chunks from the same document. This gives the user one perspective on their question when multiple sources might say different (or contradictory) things.

```python
# CONCEPT FOR ANTIGRAVITY:
# After ranking, apply Maximum Marginal Relevance (MMR) to enforce diversity.
# MMR selects results that are relevant to the query AND diverse from each other.

def apply_mmr(
    ranked_chunks: list[Chunk],
    lambda_param: float = 0.7,  # 0 = max diversity, 1 = max relevance
    top_k: int = 8
) -> list[Chunk]:
    
    selected = []
    candidates = ranked_chunks.copy()
    
    while len(selected) < top_k and candidates:
        best = None
        best_score = -1
        
        for candidate in candidates:
            relevance = candidate.rank_score
            
            if selected:
                # Penalise candidates similar to already selected chunks
                max_similarity = max(
                    cosine_similarity(candidate.embedding, s.embedding)
                    for s in selected
                )
                diversity_penalty = (1 - lambda_param) * max_similarity
            else:
                diversity_penalty = 0
            
            mmr_score = lambda_param * relevance - diversity_penalty
            
            if mmr_score > best_score:
                best_score = mmr_score
                best = candidate
        
        selected.append(best)
        candidates.remove(best)
    
    return selected
```

---

## 10. Context Engineering — How Knowledge Reaches the LLM

### The Context Window Is Prime Real Estate

Every token sent to Claude costs money and consumes attention. The way you structure the context — the system prompt, the retrieved chunks, the question — directly determines answer quality.

Context engineering is the discipline of making every token count.

### The Complete Prompt Architecture

```python
# CONCEPT FOR ANTIGRAVITY:
# Every query to Claude has this exact structure.
# Do not deviate from this structure without understanding the consequences.

SYSTEM_PROMPT = """
You are the Assest knowledge assistant for {company_name}.
Your role is to answer questions from employees based solely on the 
company's own documented knowledge.

STRICT RULES:
1. Answer ONLY using information from the provided knowledge chunks.
2. If the answer is not in the provided chunks, say exactly:
   "I couldn't find this in your company's knowledge base. 
   This might be undocumented — consider asking [relevant team] 
   or adding this to your knowledge base."
3. Never generate, guess, or infer information not present in the chunks.
4. Always cite your source using the format: [Source: {document_title}]
5. If chunks contain conflicting information, present both and note the conflict.
6. If a chunk is marked as potentially stale, note this in your answer.

RESPONSE FORMAT:
- Be direct and concise. This is a work tool, not a chatbot.
- Lead with the answer, then the supporting detail.
- Use bullet points for multi-step processes.
- End with source citations.
- Maximum 400 words unless the question requires more detail.
"""

USER_PROMPT_TEMPLATE = """
QUESTION: {question}

RELEVANT KNOWLEDGE:
{formatted_chunks}

Please answer the question based only on the above knowledge.
"""

def format_chunks_for_context(chunks: list[Chunk]) -> str:
    """
    WHY this formatting matters:
    Claude attends to structure. Well-formatted context is easier to
    reason about than a wall of text. Each chunk gets:
    - A clear separator
    - Its source and tier prominently displayed
    - A staleness warning if applicable
    - The content itself
    """
    formatted = []
    for i, chunk in enumerate(chunks, 1):
        stale_warning = ""
        if chunk.is_potentially_stale:
            stale_warning = "\n⚠️ NOTE: This content may be outdated."
        
        formatted.append(f"""
--- Knowledge Chunk {i} ---
Source: {chunk.document_title}
Section: {chunk.section_heading}
Type: {chunk.content_type} (Tier {chunk.content_tier})
Last Updated: {chunk.source_modified_at.strftime('%B %Y')}
URL: {chunk.source_url}
{stale_warning}

{chunk.content}
""")
    
    return "\n".join(formatted)
```

### Handling the "I Don't Know" Case Well

When the system cannot find relevant knowledge, the response matters enormously. A bad "I don't know" destroys trust. A good one is itself useful.

```python
# CONCEPT FOR ANTIGRAVITY:
# When knowledge is not found (no chunks above similarity threshold),
# do NOT call Claude at all — it has nothing to work with.
# Instead, return a structured "knowledge gap" response.

class KnowledgeGapResponse:
    message: str = "I couldn't find this in your company's knowledge base."
    
    suggested_actions: list[str] = [
        "Ask your team directly and then document the answer in Notion",
        "Check if this is covered in a tool we haven't connected yet",
        "This might be a knowledge gap worth filling — consider creating a doc"
    ]
    
    # Log the unanswered question — this is valuable signal
    # Questions that can't be answered are implicit knowledge that
    # needs to be captured. Surface these in the admin dashboard.
    gap_logged: bool = True
    gap_type: str = "no_relevant_knowledge"
```

---

## 11. Memory Architecture — How the System Remembers

### The Four Types of Memory in Assest

**Type 1 — In-context memory (per query)**
The retrieved chunks in the current query's context window. This is temporary — it exists only for the duration of one API call. Every query starts fresh.

**Type 2 — Episodic memory (session)**
For the web chat interface, conversation history within a single session. The user asked a question, got an answer, then asked a follow-up. The follow-up needs the previous context to make sense.

```python
# CONCEPT FOR ANTIGRAVITY:
# For multi-turn conversations in the web chat, maintain a session store.
# Session store: Redis with TTL of 30 minutes (session expires after inactivity)
# 
# Each session stores: list of (question, answer) pairs
# Maximum session history: last 5 turns (to manage context size)
# 
# On each query, append the last 3 turns to the user prompt before the question.
# This allows follow-up questions like "tell me more about the third point"
# to work correctly.

SESSION_HISTORY_TEMPLATE = """
Previous conversation context:
{history}

Current question: {question}
"""
```

**Type 3 — Semantic memory (persistent)**
The entire Qdrant vector store. This is the long-term knowledge of the system. Everything ingested lives here until explicitly deleted.

**Type 4 — Procedural memory (skills files)**
Structured workflows extracted from semantic memory. These represent the "how to do things" knowledge in executable form. This is Phase 3.

### The Feedback Loop — How the System Learns

Every thumbs up / thumbs down on an answer feeds back into the ranking system. Over time, chunks that consistently produce good answers get higher quality scores and are ranked higher. Chunks that produce bad answers get lower scores.

```python
# CONCEPT FOR ANTIGRAVITY:
# When a user submits feedback on an answer:
# 1. Update QueryLog with feedback (positive/negative)
# 2. For each source chunk used in that answer:
#    - If positive: increment positive_feedback count in both
#      PostgreSQL and Qdrant payload
#    - If negative: increment negative_feedback count
# 3. Recompute quality_score: positive / (positive + negative)
# 4. Update Qdrant payload with new quality_score
# 5. This score is used in the ranking formula (Signal 5 above)
# 
# Over 1000 queries, this creates a self-improving retrieval system.
# Chunks that help users get promoted. Chunks that mislead get demoted.
```

---

## 12. The Knowledge Graph — How Relationships Are Understood

### Why a Graph, Not Just Vectors

Vectors capture semantic similarity. They answer "what content is similar to this query?"

A knowledge graph captures relationships. It answers "who owns this process?", "which documents reference this decision?", "what happens downstream if this policy changes?"

These are different questions. A company brain needs both.

### The Entity Types in Assest's Knowledge Graph

```python
# CONCEPT FOR ANTIGRAVITY:
# The knowledge graph is built on top of the ingested content.
# It runs asynchronously — it does not block ingestion.
# It uses Neo4j (or a PostgreSQL adjacency list for MVP).
# 
# Node types (entities):
# - Document: a source document (Notion page, Google Doc, etc.)
# - Person: an anonymised author or decision-maker
# - Team: a department or group
# - Process: a named business process ("customer refund")
# - Policy: a rule or guideline
# - Decision: a recorded decision with date and context
# - System: a tool or system mentioned in documents
# 
# Edge types (relationships):
# - Document --DESCRIBES--> Process
# - Document --CONTAINS--> Policy
# - Document --REFERENCES--> Document
# - Person --AUTHORED--> Document
# - Team --OWNS--> Process
# - Decision --AFFECTS--> Policy
# - Process --DEPENDS_ON--> System
# - Policy --SUPERSEDES--> Policy (when a newer version exists)
```

### MVP Graph Implementation (PostgreSQL, No Neo4j)

For MVP, a full graph database is overkill. Use PostgreSQL adjacency list tables:

```sql
-- CONCEPT FOR ANTIGRAVITY:
-- Simple graph tables in PostgreSQL for MVP.
-- Migrate to Neo4j when graph queries become complex.

CREATE TABLE graph_nodes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id VARCHAR NOT NULL,
    node_type VARCHAR NOT NULL,  -- 'document', 'person', 'team', 'process', 'policy'
    label VARCHAR NOT NULL,      -- human-readable name
    properties JSONB,            -- type-specific attributes
    source_chunk_id UUID,        -- which chunk this was extracted from
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE graph_edges (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id VARCHAR NOT NULL,
    source_node_id UUID REFERENCES graph_nodes(id),
    target_node_id UUID REFERENCES graph_nodes(id),
    relationship_type VARCHAR NOT NULL,  -- 'DESCRIBES', 'REFERENCES', 'OWNS', etc.
    properties JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for graph traversal:
CREATE INDEX idx_graph_edges_source ON graph_edges(source_node_id);
CREATE INDEX idx_graph_edges_target ON graph_edges(target_node_id);
CREATE INDEX idx_graph_nodes_workspace ON graph_nodes(workspace_id, node_type);
```

### Entity Extraction — Building the Graph Automatically

```python
# CONCEPT FOR ANTIGRAVITY:
# After a document is ingested, run entity extraction asynchronously.
# Use Claude to extract entities and relationships from each chunk.
# This is a Celery task that runs after the ingestion pipeline completes.

ENTITY_EXTRACTION_PROMPT = """
Extract entities and relationships from this text.
Return a JSON object with:
{
  "entities": [
    {"type": "Person|Team|Process|Policy|System|Decision", "label": "name", "properties": {}}
  ],
  "relationships": [
    {"source": "entity label", "type": "RELATIONSHIP_TYPE", "target": "entity label"}
  ]
}

Only extract clearly mentioned entities. Do not infer.
Text: {chunk_content}
"""
# Temperature: 0
# Model: claude-haiku (cheaper for extraction, not answering)
```

---

## 13. AI Agent Orchestration — How Agents Work Together

### The Agent Mental Model

An AI agent is a system that:
1. Receives a goal
2. Decides what actions to take
3. Takes actions (calls tools, queries knowledge, makes API calls)
4. Observes results
5. Decides next actions based on results
6. Repeats until goal is achieved or it determines it cannot proceed

The key difference from a simple LLM call is the loop — the agent can take multiple steps, each informed by the previous step's result.

### Agent Types in Assest

**Type 1 — Query Agent (MVP)**
The simplest agent. One-shot: receives a question, retrieves knowledge, generates answer.
No loop needed — one question, one answer.

**Type 2 — Ingestion Monitor Agent (Phase 1)**
Runs on a schedule. Checks connector sync status. Retries failed syncs. Alerts on errors.
Simple loop: check → act if needed → report.

**Type 3 — Knowledge Gap Agent (Phase 2)**
Analyses unanswered questions. Identifies patterns. Recommends what documentation to create.
Multi-step: aggregate gaps → cluster by topic → generate recommendations → notify admin.

**Type 4 — Skills Extraction Agent (Phase 3)**
Reads all ingested knowledge. Identifies process patterns. Extracts structured skills files.
Complex multi-step with tool use: retrieve → analyse → extract → validate → store.

**Type 5 — Customer Support Agent (Assest internal)**
Monitors support inbox. Classifies issues. Attempts resolution. Drafts responses.
Full agentic loop with human-in-the-loop escalation.

### The Agent Framework — LangGraph

LangGraph models agents as state machines. Each node in the graph is an action. Each edge is a transition condition.

```python
# CONCEPT FOR ANTIGRAVITY:
# The Query Agent as a LangGraph state machine.
# This is the simplest agent — useful to understand the pattern.

from langgraph.graph import StateGraph, END
from typing import TypedDict

class QueryState(TypedDict):
    question: str
    workspace_id: str
    retrieved_chunks: list
    ranked_chunks: list
    answer: str
    sources: list
    knowledge_found: bool
    error: str

# Define the nodes (actions):
def retrieve_knowledge(state: QueryState) -> QueryState:
    """Search vector DB and keyword index"""
    # ... call retriever ...
    return {**state, "retrieved_chunks": results, "knowledge_found": len(results) > 0}

def rank_results(state: QueryState) -> QueryState:
    """Apply ranking formula and MMR"""
    # ... call ranker ...
    return {**state, "ranked_chunks": ranked}

def generate_answer(state: QueryState) -> QueryState:
    """Call Claude with ranked chunks"""
    # ... call generator ...
    return {**state, "answer": answer, "sources": sources}

def handle_no_knowledge(state: QueryState) -> QueryState:
    """Return knowledge gap response"""
    return {**state, "answer": "Knowledge not found response..."}

# Define the graph:
graph = StateGraph(QueryState)
graph.add_node("retrieve", retrieve_knowledge)
graph.add_node("rank", rank_results)
graph.add_node("generate", generate_answer)
graph.add_node("no_knowledge", handle_no_knowledge)

graph.set_entry_point("retrieve")
graph.add_edge("retrieve", "rank")
graph.add_conditional_edges(
    "rank",
    lambda state: "generate" if state["knowledge_found"] else "no_knowledge"
)
graph.add_edge("generate", END)
graph.add_edge("no_knowledge", END)

query_agent = graph.compile()
```

### Human-in-the-Loop — When Agents Must Stop

Not every situation should be handled autonomously. Assest agents must know when to stop and ask for human input.

```python
# CONCEPT FOR ANTIGRAVITY:
# Every agent must have explicit escalation conditions.
# When an escalation condition is met, the agent:
# 1. Stops its current action
# 2. Saves its current state
# 3. Sends a notification to the human (Slack DM or email)
# 4. Waits for human input before continuing
# 5. Resumes from saved state after input received

ESCALATION_CONDITIONS = {
    "support_agent": [
        "confidence_score < 0.7",          # Not sure of the answer
        "issue_type == 'billing'",           # Money is involved
        "issue_type == 'data_deletion'",     # Compliance critical
        "consecutive_failures >= 2",         # Two failed attempts
        "customer_sentiment == 'angry'"      # Human empathy needed
    ],
    "ingestion_agent": [
        "connector_auth_failed",             # Need human to re-authenticate
        "pii_detected_in_unexpected_field",  # Human should review
        "document_count_dropped_by_50pct"   # Source may have been deleted
    ]
}
```

---

## 14. Skills File System — How Knowledge Becomes Action

### The Progression from Text to Action

```
RAW TEXT                    "Refunds can be processed within 5 days if the 
(in Notion)                 order is under 30 days old and the reason is valid"

         ↓ INGEST

VECTOR CHUNK                Embedded, stored, retrievable by semantic search
(in Qdrant)

         ↓ EXTRACT SKILL

STRUCTURED SKILL            {
(JSON)                        "trigger": "customer requests refund",
                              "conditions": [
                                {"check": "order_age_days", "operator": "<", "value": 30},
                                {"check": "refund_reason", "operator": "in", 
                                 "value": ["defective", "wrong_item", "not_delivered"]}
                              ],
                              "action": "approve_refund",
                              "else_action": "escalate_to_manager"
                            }

         ↓ AGENT USES SKILL

EXECUTABLE ACTION           Agent reads skill, checks conditions against
(in runtime)                actual order data, takes the correct action
                            without human intervention
```

### The Skills File Schema

```json
{
    "skill_id": "handle_customer_refund_v2",
    "skill_name": "Customer Refund Handling",
    "version": "2.0",
    "workspace_id": "ws_abc123",
    
    "metadata": {
        "created_at": "2024-01-15T00:00:00Z",
        "last_updated": "2024-03-20T00:00:00Z",
        "source_documents": [
            "https://notion.so/page/xyz",
            "https://docs.google.com/doc/abc"
        ],
        "confidence_score": 0.92,
        "times_executed": 234,
        "success_rate": 0.94,
        "owner_team": "customer_success"
    },
    
    "triggers": [
        "customer requests refund",
        "order cancellation with refund",
        "money back request"
    ],
    
    "required_inputs": [
        {"name": "order_id", "type": "string", "required": true},
        {"name": "order_date", "type": "datetime", "required": true},
        {"name": "refund_reason", "type": "string", "required": true},
        {"name": "order_amount", "type": "number", "required": true}
    ],
    
    "steps": [
        {
            "step_id": "check_eligibility",
            "step_type": "condition",
            "condition": {
                "operator": "AND",
                "checks": [
                    {"field": "order_age_days", "operator": "<", "value": 30},
                    {
                        "field": "refund_reason",
                        "operator": "in",
                        "value": ["defective", "wrong_item", "not_delivered", "quality_issue"]
                    }
                ]
            },
            "if_true": "approve_refund",
            "if_false": "check_exception_eligibility"
        },
        {
            "step_id": "approve_refund",
            "step_type": "action",
            "action": "issue_refund",
            "parameters": {
                "amount": "{{order_amount}}",
                "method": "original_payment_method",
                "timeline": "5_business_days"
            },
            "notify": ["customer", "finance_team"],
            "next_step": "END"
        },
        {
            "step_id": "check_exception_eligibility",
            "step_type": "condition",
            "condition": {
                "field": "order_age_days",
                "operator": "<",
                "value": 60
            },
            "if_true": "escalate_to_manager",
            "if_false": "decline_refund"
        },
        {
            "step_id": "escalate_to_manager",
            "step_type": "human_handoff",
            "message": "Order is 30-60 days old. Manager review required.",
            "escalate_to": "customer_success_manager",
            "timeout_hours": 24,
            "next_step": "END"
        },
        {
            "step_id": "decline_refund",
            "step_type": "action",
            "action": "send_decline_message",
            "parameters": {
                "template": "refund_decline_outside_window",
                "reason": "order_outside_return_window"
            },
            "next_step": "END"
        }
    ]
}
```

---

## 15. Metadata Design — The Hidden Layer That Makes Everything Work

### Why Metadata Is As Important As Content

Content is what the system knows. Metadata is how the system knows what it knows.

Without metadata:
- You cannot filter results by date
- You cannot rank by tier
- You cannot detect staleness
- You cannot enforce permissions
- You cannot show citations
- You cannot explain why an answer was given

Every architectural decision in Assest depends on metadata being correct, complete, and indexed.

### The Metadata Taxonomy

```python
# CONCEPT FOR ANTIGRAVITY:
# Every piece of stored knowledge has these metadata categories.
# Never store content without complete metadata.

METADATA_TAXONOMY = {
    
    # IDENTITY — who is this, where did it come from
    "workspace_id": "required, indexed, filter on every query",
    "document_id": "required, links chunk to its parent document",
    "chunk_id": "required, primary key",
    "connector_id": "required, which integration provided this",
    "source_id": "required, ID in the source system for incremental sync",
    "source_url": "required, must be a working deep link",
    
    # TEMPORAL — when, and is it still valid
    "source_created_at": "when the original document was created",
    "source_modified_at": "when the document was last changed — drives staleness",
    "ingested_at": "when Assest processed this version",
    "expires_at": "when this should be re-evaluated (tier-dependent)",
    "is_stale": "boolean — computed from expires_at and modification signals",
    
    # CLASSIFICATION — what kind of thing is this
    "content_tier": "1, 2, or 3 — drives ranking weight",
    "content_type": "policy|runbook|decision|ticket|thread|doc|other",
    "topic_cluster": "inferred topic group (for knowledge gap analysis)",
    "language": "detected language code — for multilingual support",
    
    # QUALITY — how good and trustworthy is this
    "quality_score": "float 0-1, computed from feedback",
    "retrieval_count": "how many times retrieved — indicates relevance",
    "positive_feedback": "thumbs up count",
    "negative_feedback": "thumbs down count",
    "confidence_score": "confidence of extraction/classification — not LLM confidence",
    
    # ACCESS CONTROL — who can see this
    "visibility": "all|engineering|hr|exec|custom",
    "allowed_agent_types": "which agent types can use this knowledge",
    "sensitivity_level": "public|internal|confidential",
    
    # STRUCTURE — how does this fit in the larger document
    "chunk_index": "position in parent document",
    "total_chunks": "total chunks in parent document",
    "section_heading": "nearest heading above this chunk",
    "parent_chunk_id": "for hierarchical chunking",
    "document_title": "title of parent document"
}
```

---

## 16. Database Architecture — Where Everything Lives

### The Three-Database Pattern

Assest uses three storage systems, each for a specific purpose:

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   POSTGRESQL    │    │     QDRANT      │    │   AWS S3        │
│   (Supabase)    │    │  (Self-hosted)  │    │  (Mumbai)       │
├─────────────────┤    ├─────────────────┤    ├─────────────────┤
│ Structured data │    │ Vector search   │    │ Raw file storage │
│ Relationships   │    │ Embeddings      │    │ Audit archives  │
│ User accounts   │    │ Chunk content   │    │ Backup storage  │
│ Workspace config│    │ Semantic search │    │ Large documents │
│ Query logs      │    │                 │    │                 │
│ Audit logs      │    │                 │    │                 │
│ Connector config│    │                 │    │                 │
│ Skills files    │    │                 │    │                 │
│ Graph nodes     │    │                 │    │                 │
│ FTS search index│    │                 │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

### PostgreSQL Schema — Complete Table Definitions

```sql
-- CONCEPT FOR ANTIGRAVITY:
-- These are the core tables. Build them in this order.
-- Use Alembic for migrations. Never ALTER TABLE in production manually.

-- Workspaces (customers)
CREATE TABLE workspaces (
    id VARCHAR(20) PRIMARY KEY,  -- format: ws_[random]
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(100) UNIQUE NOT NULL,
    api_key_hash VARCHAR(255) NOT NULL,
    plan VARCHAR(50) DEFAULT 'starter',
    settings JSONB DEFAULT '{}',
    is_active BOOLEAN DEFAULT TRUE,
    trial_ends_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Connectors (data source configurations)
CREATE TABLE connectors (
    id VARCHAR(20) PRIMARY KEY,  -- format: conn_[random]
    workspace_id VARCHAR(20) REFERENCES workspaces(id) ON DELETE CASCADE,
    connector_type VARCHAR(50) NOT NULL,  -- 'notion'|'google_drive'|'slack'|'github'
    display_name VARCHAR(255) NOT NULL,
    config_encrypted TEXT NOT NULL,  -- Fernet-encrypted JSON
    status VARCHAR(50) DEFAULT 'pending',  -- 'active'|'paused'|'error'|'pending'
    sync_schedule VARCHAR(50) DEFAULT '0 */6 * * *',  -- cron format
    last_synced_at TIMESTAMPTZ,
    last_sync_cursor TEXT,  -- pagination token for incremental sync
    last_error TEXT,
    document_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Documents (ingested source documents)
CREATE TABLE documents (
    id VARCHAR(20) PRIMARY KEY,  -- format: doc_[random]
    workspace_id VARCHAR(20) REFERENCES workspaces(id) ON DELETE CASCADE,
    connector_id VARCHAR(20) REFERENCES connectors(id) ON DELETE CASCADE,
    source_id VARCHAR(500) NOT NULL,  -- ID in source system
    source_url TEXT NOT NULL,
    title TEXT NOT NULL,
    content_hash VARCHAR(64) NOT NULL,  -- SHA256 for deduplication
    content_tier INTEGER DEFAULT 2,
    content_type VARCHAR(50) DEFAULT 'doc',
    chunk_count INTEGER DEFAULT 0,
    source_created_at TIMESTAMPTZ,
    source_modified_at TIMESTAMPTZ NOT NULL,
    ingested_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ,
    is_stale BOOLEAN DEFAULT FALSE,
    s3_raw_key TEXT,  -- path in S3 bucket for raw content
    UNIQUE(workspace_id, source_id)
);

-- Chunks (document segments stored in Qdrant — metadata mirror)
CREATE TABLE chunks (
    id UUID PRIMARY KEY,  -- matches Qdrant point ID
    workspace_id VARCHAR(20) REFERENCES workspaces(id) ON DELETE CASCADE,
    document_id VARCHAR(20) REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    total_chunks INTEGER NOT NULL,
    content TEXT NOT NULL,
    content_tokens INTEGER NOT NULL,
    content_tier INTEGER NOT NULL,
    content_type VARCHAR(50) NOT NULL,
    section_heading TEXT,
    source_url TEXT NOT NULL,
    document_title TEXT NOT NULL,
    source_modified_at TIMESTAMPTZ NOT NULL,
    ingested_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ,
    is_stale BOOLEAN DEFAULT FALSE,
    retrieval_count INTEGER DEFAULT 0,
    positive_feedback INTEGER DEFAULT 0,
    negative_feedback INTEGER DEFAULT 0,
    quality_score FLOAT DEFAULT 0.5,
    search_vector tsvector,  -- for BM25 full-text search
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_chunks_workspace ON chunks(workspace_id);
CREATE INDEX idx_chunks_document ON chunks(document_id);
CREATE INDEX idx_chunks_search ON chunks USING GIN(search_vector);
CREATE INDEX idx_chunks_modified ON chunks(source_modified_at);
CREATE INDEX idx_chunks_quality ON chunks(quality_score);

-- Query logs
CREATE TABLE query_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id VARCHAR(20) REFERENCES workspaces(id),
    question TEXT NOT NULL,
    answer TEXT,
    source_chunk_ids UUID[],  -- which chunks were used
    knowledge_found BOOLEAN NOT NULL,
    feedback VARCHAR(20),  -- 'positive'|'negative'|null
    response_time_ms INTEGER,
    tokens_used INTEGER,
    interface VARCHAR(50),  -- 'slack'|'web'
    user_hash VARCHAR(64),  -- anonymised user identifier
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_query_logs_workspace ON query_logs(workspace_id, created_at);
CREATE INDEX idx_query_logs_no_knowledge ON query_logs(workspace_id) 
    WHERE knowledge_found = FALSE;  -- for knowledge gap analysis

-- Audit logs (immutable — no updates or deletes)
CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id VARCHAR(20),
    event_type VARCHAR(100) NOT NULL,
    actor_id VARCHAR(255),
    resource_type VARCHAR(100),
    resource_id VARCHAR(255),
    metadata JSONB,
    ip_address INET,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
-- No foreign keys on audit_logs intentionally.
-- Audit logs must survive even if the workspace is deleted.
-- Partition by month for 180-day retention management.
CREATE INDEX idx_audit_workspace ON audit_logs(workspace_id, created_at);

-- Skills files
CREATE TABLE skills (
    id VARCHAR(20) PRIMARY KEY,  -- format: skill_[random]
    workspace_id VARCHAR(20) REFERENCES workspaces(id) ON DELETE CASCADE,
    skill_name VARCHAR(255) NOT NULL,
    version VARCHAR(20) NOT NULL DEFAULT '1.0',
    skill_definition JSONB NOT NULL,  -- the complete skills file JSON
    source_document_ids VARCHAR(20)[],
    confidence_score FLOAT,
    times_executed INTEGER DEFAULT 0,
    success_rate FLOAT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## 17. Data Flow Diagrams — The Complete Picture

### Ingestion Flow (Detailed)

```
SCHEDULED TRIGGER (Celery Beat — every 6hrs for Notion)
    │
    ▼
LOAD CONNECTOR CONFIG
    │ Decrypt OAuth token from PostgreSQL
    │ Load last_sync_cursor
    ▼
CONNECTOR.FETCH_DOCUMENTS(since=last_sync_cursor)
    │ Returns: Iterator[RawDocument]
    │ Each document: title, raw_content, source_url, modified_at, content_hash
    ▼
FOR EACH DOCUMENT:
    │
    ├── CHECK CONTENT HASH
    │       If hash == stored hash: SKIP (content unchanged)
    │       If hash != stored hash OR new document: CONTINUE
    │
    ├── UPLOAD RAW TO S3
    │       Key: {workspace_id}/{connector_id}/{source_id}/raw_{timestamp}
    │       Purpose: audit trail, debugging, re-processing without re-fetching
    │
    ├── PARSE (Unstructured.io)
    │       Input: raw content (any format)
    │       Output: clean plain text + structure hints
    │
    ├── CLASSIFY
    │       Input: title + first 200 tokens of content
    │       LLM call: "What type of document is this? Policy/Runbook/Decision/Ticket/Thread/Doc"
    │       Output: content_type, content_tier
    │
    ├── PII SCRUB (Presidio)
    │       Detect: Aadhaar, PAN, phone, email, name
    │       Replace with: [AADHAAR_NUMBER], [PAN_NUMBER], etc.
    │       Log: entity types found (not values) to audit_log
    │
    ├── CHUNK (LlamaIndex SentenceSplitter)
    │       Strategy based on content_type
    │       Output: list[Chunk] with metadata
    │
    ├── EMBED (OpenAI text-embedding-3-small)
    │       Batch 100 chunks per API call
    │       Output: each chunk now has embedding: list[float] (1536 dims)
    │
    ├── STORE VECTORS (Qdrant)
    │       Upsert all chunks as points
    │       Delete old chunks for this document_id (if document was updated)
    │
    ├── STORE METADATA (PostgreSQL)
    │       Upsert document record
    │       Upsert chunk records
    │       Update document.chunk_count
    │
    ├── UPDATE FTS INDEX (PostgreSQL)
    │       Trigger auto-updates search_vector column
    │
    ├── SET STALENESS TIMER
    │       Tier 1: expires_at = now + 90 days
    │       Tier 2: expires_at = now + 30 days
    │       Tier 3: expires_at = now + 7 days
    │
    └── AUDIT LOG
            Event: 'document_ingested'
            Metadata: {document_id, chunk_count, pii_entities_found}

AFTER ALL DOCUMENTS:
    Update connector.last_synced_at = now
    Update connector.last_sync_cursor = new cursor
    Update connector.document_count
    Log: 'connector_sync_completed'
```

### Query Flow (Detailed)

```
USER SUBMITS QUESTION via Slack or Web Chat
    │
    ▼
API RECEIVES POST /query
    │ Validate: API key → load workspace
    │ Validate: question is not empty
    │ Validate: question length < 1000 chars
    │ Rate limit check: < 20 req/min for this workspace
    ▼
EMBED QUESTION
    │ Model: text-embedding-3-small
    │ Output: query_vector (1536 floats)
    ▼
PARALLEL RETRIEVAL
    ├── VECTOR SEARCH (Qdrant)
    │       Filter: workspace_id = this workspace
    │       Filter: is_stale = false
    │       Top K: 15 results with similarity scores
    │
    └── KEYWORD SEARCH (PostgreSQL FTS)
            Filter: workspace_id = this workspace
            Query: plainto_tsquery('english', question)
            Top K: 15 results with rank scores
    │
    ▼
COMBINE (Reciprocal Rank Fusion)
    │ Union of both result sets
    │ Compute RRF score for each unique chunk
    │ Sort by RRF score
    ▼
APPLY METADATA FILTERS
    │ Remove is_stale = true (if not already filtered)
    │ Apply workspace access control rules
    │ Remove chunks below quality_score threshold (< 0.2)
    ▼
RANK (Multi-signal scoring)
    │ Compute: semantic + keyword + tier + recency + quality scores
    │ Sort by composite score
    ▼
DIVERSITY (MMR)
    │ Select top 8 diverse chunks from ranked list
    │ Ensure no more than 3 chunks from same document
    ▼
CHECK KNOWLEDGE FOUND
    │ If 0 chunks found OR max similarity < 0.70:
    │     Return KnowledgeGapResponse
    │     Log unanswered question to query_logs
    │     Return (no Claude call)
    │
    ▼ (knowledge found)
ASSEMBLE CONTEXT
    │ Format: system_prompt + formatted_chunks + question
    │ Calculate total tokens — ensure < 100K (safe limit)
    ▼
CALL CLAUDE API
    │ Model: claude-sonnet-4-20250514
    │ Temperature: 0
    │ Max tokens: 800
    │ System prompt: Assest knowledge assistant instructions
    ▼
PARSE RESPONSE
    │ Extract answer text
    │ Extract cited sources (parse [Source: X] markers)
    │ Compute response_time_ms
    ▼
LOG TO QUERY_LOGS
    │ question, answer, source_chunk_ids, response_time_ms, tokens_used
    ▼
UPDATE RETRIEVAL COUNTS
    │ Increment retrieval_count for each used chunk (async)
    ▼
RETURN RESPONSE TO CLIENT
    │ Format for Slack or web based on request
    │ Include answer, sources, query_id (for feedback)
```

---

## 18. Failure Modes — What Goes Wrong and Why

### The Most Common Failures and Their Fixes

**Failure 1 — Hallucination despite grounding**
Symptom: Claude gives an answer that is not in the retrieved chunks.
Cause: System prompt not strict enough, or context contains loosely related chunks that Claude "completes" incorrectly.
Fix: Tighten system prompt. Add "Do not infer, extrapolate, or complete information. Only state what is explicitly in the chunks." Raise similarity threshold to 0.75.

**Failure 2 — Wrong chunk retrieved (low retrieval precision)**
Symptom: Answer is accurate but from a different topic. User reports "that's not what I asked."
Cause: Question is ambiguous, or chunks are too large (pulling in irrelevant content).
Fix: Reduce chunk size. Improve section heading metadata (section headings help the model understand what a chunk is about). Add question clarification step for ambiguous queries.

**Failure 3 — Correct chunk exists but not retrieved (low recall)**
Symptom: System says "knowledge not found" but the answer is definitely in a Notion page.
Cause: Chunk embedding is not close to question embedding. Usually because the question uses different terminology than the document.
Fix: Add query expansion — generate 2-3 alternative phrasings of the question and retrieve for all of them. Use hybrid retrieval (BM25 catches exact term matches that vector search misses).

**Failure 4 — Stale knowledge returned as current**
Symptom: User gets an answer based on an old policy that has been updated.
Cause: Staleness detection not working, or re-sync frequency too low.
Fix: Shorten re-sync intervals. Add explicit staleness warnings in answer format. Show source last-modified date with every answer.

**Failure 5 — Ingestion silently fails**
Symptom: New documents added to Notion but not appearing in answers.
Cause: Connector sync crashed midway. Error not surfaced.
Fix: Implement dead-letter queue for failed jobs. Alert on connector last_synced_at > 2x sync schedule interval. Show connector health prominently in admin dashboard.

**Failure 6 — PII in answers**
Symptom: Answer contains a real phone number or email.
Cause: PII scrubber missed a pattern. New PII format not covered.
Fix: Treat PII scrubbing failures as blocking errors, not warnings. Add Indian-specific PII patterns proactively. Run monthly audit of random samples from Qdrant.

**Failure 7 — Multi-tenant data leak**
Symptom: Workspace A sees knowledge from Workspace B.
Cause: workspace_id filter missing from a query path.
Fix: Add integration test that explicitly verifies workspace isolation. Use a secondary workspace in all tests and assert its content never appears. Make workspace_id filter a middleware-level requirement, not a per-query option.

---

## 19. Scaling Strategy — How the System Grows

### MVP Scale Targets (0-3 months)
- Workspaces: 1-5
- Documents: up to 2,000 per workspace
- Chunks: up to 10,000 total
- Queries per day: up to 500
- Infrastructure: single EC2 t3.medium

At this scale, everything in docker-compose on one server is fine.

### Growth Scale Targets (3-12 months)
- Workspaces: 5-50
- Documents: up to 10,000 per workspace
- Chunks: up to 500,000 total
- Queries per day: up to 10,000
- Infrastructure: begins to separate

Changes needed at this scale:
- Move PostgreSQL to RDS (managed, automatic backups, read replicas)
- Move Redis to ElastiCache (managed, no manual maintenance)
- Qdrant: upgrade to 3-node cluster for redundancy
- Separate Celery workers onto their own EC2 instances
- Add CDN (CloudFront) for web chat frontend

### Scale Triggers and Actions

```
IF query_response_time > 5s:
    → Add Qdrant read replica
    → Add API server (load balancer in front of 2 EC2 instances)
    → Review chunk retrieval count (reduce top_k if too high)

IF ingestion_jobs taking > 30min:
    → Add dedicated Celery worker instance
    → Implement priority queues (Tier 1 docs ingested before Tier 3)

IF PostgreSQL query_time > 100ms:
    → Add read replica for query logs and analytics
    → Archive old query_logs to S3 (keep only last 90 days in DB)

IF Qdrant disk > 70% full:
    → Expand volume
    → Review and purge chunks for deleted documents
    → Consider chunk deduplication across workspaces (Phase 4)
```

---

## 20. Antigravity Prompting Patterns for This Architecture

### The Master Context Block

Paste this at the start of EVERY Antigravity session. Every time. Without exception.

```
=== ASSEST ARCHITECTURE CONTEXT ===

Product: Assest — Company brain for Indian startups
Philosophy: Grounded (never hallucinate), Current (detect stale content),
            Structured (text → skills), Permissioned (workspace isolation),
            Explainable (always cite sources)

Stack: Python 3.11, FastAPI, Qdrant, PostgreSQL/Supabase, Celery/Redis,
       Claude API (claude-sonnet-4-20250514), OpenAI embeddings (text-embedding-3-small),
       Presidio (PII), LlamaIndex (chunking), Next.js 14 (frontend)

Multi-tenancy: workspace_id is on EVERY database query and Qdrant filter.
               This is non-negotiable. Never write a query without it.

Data location: All data in AWS Mumbai (ap-south-1). No data crosses borders.

Current file I am working on: [SPECIFY]
Current phase: [Phase 1 / 2 / 3 / 4]
What I need: [SPECIFY EXACTLY]
===
```

### Pattern 1 — Building a New Component

```
[Paste master context block]

I need to build [component name] for Assest.

Here is what this component must do: [paste the WHY section from this document]

Here is the interface it must implement:
- Input: [describe exact inputs]
- Output: [describe exact outputs]
- Dependencies: [list what it calls]
- Called by: [what calls it]

Constraints:
- [constraint 1]
- [constraint 2]

Please build this as a Python module in backend/[path]/[filename].py.
Include type hints, docstrings, error handling for [list failure modes].
```

### Pattern 2 — Debugging a Failure

```
[Paste master context block]

I have a bug in [component name].

Symptom: [describe what the user sees]
Expected: [describe what should happen]
Actual: [describe what happens instead]

Error (if any):
[paste full traceback]

Relevant code:
[paste the file contents]

Based on the failure modes described in the architecture document,
I believe this might be [your hypothesis]. Please diagnose and fix.
```

### Pattern 3 — Writing Tests

```
[Paste master context block]

Write pytest tests for backend/[path]/[filename].py

The component does: [one sentence description]

Test these specific behaviours:
1. [behaviour 1 — what input produces what output]
2. [behaviour 2]
3. [failure case 1 — what should happen when X fails]
4. [failure case 2]

Mocking requirements:
- Mock all external API calls (Notion, Google, Anthropic, OpenAI)
- Use pytest fixtures for Qdrant (use qdrant-client's in-memory mode)
- Use pytest fixtures for PostgreSQL (use a test database, not production)

Each test must be independent. No test should depend on another test's state.
```

### Pattern 4 — Adding a New Connector

```
[Paste master context block]

I need to add a new [SOURCE_NAME] connector to Assest.

The connector must:
- Inherit from backend/connectors/base.py BaseConnector
- Implement: validate_config(), connect(), fetch_documents(since=), get_sync_metadata()
- Return RawDocument objects (see the RawDocument specification in the architecture doc)
- Handle incremental sync using [describe the API's cursor/timestamp mechanism]
- Handle rate limiting: [describe the API's rate limits]
- Handle auth: [OAuth / API key / etc.]

The [SOURCE_NAME] API documentation for these endpoints:
- [paste relevant API docs or describe the endpoints]

Connector config (what gets stored encrypted in database):
- [field 1]: [description]
- [field 2]: [description]

Error cases to handle:
- Invalid credentials: [what the API returns]
- Rate limit: [what the API returns]
- Not found: [what the API returns]
```

---

*Architecture version: 1.0*
*Companion to: assest_blueprint.md*
*This document explains WHY. The blueprint explains HOW. Read both before coding.*
*For Antigravity AI IDE — paste relevant sections before each task*
