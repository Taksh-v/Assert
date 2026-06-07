# Assest — Semantic Knowledge Layer Spec

## Purpose

This document defines the first production-grade semantic layer for Assest: a business glossary, ontology seed, and graph/schema mapping that can be used by retrieval, reasoning, memory, and governance modules.

The goal is to make the system understand what company data means, not just where it is stored.

## Design Goals

- Provide a canonical vocabulary for core business entities.
- Encode relationships that matter for retrieval and reasoning.
- Preserve provenance, ownership, and sensitivity metadata.
- Support both graph traversal and SQL-backed analytics.
- Stay small enough to seed quickly, but deep enough to extend safely.

## Machine-Friendly Ontology Spec (YAML)

```yaml
version: "1.0"
namespace: assest.semantic
entities:
  Customer:
    description: "A person or company that buys or uses Assest-tracked services"
    sensitivity: internal
    properties:
      name: string
      domain: string
      industry: string
  Contract:
    description: "A commercial agreement that governs service terms, pricing, and entitlements"
    sensitivity: confidential
    properties:
      contract_id: string
      value: number
      currency: string
      start_date: date
      end_date: date
  Product:
    description: "A sellable or supported offering"
    sensitivity: public
    properties:
      sku: string
      version: string
      family: string
  Invoice:
    description: "A bill or charge artifact generated for a customer"
    sensitivity: confidential
    properties:
      invoice_num: string
      amount: number
      due_date: date
      status: paid|pending|overdue
  Ticket:
    description: "A support or operations request"
    sensitivity: internal
    properties:
      ticket_id: string
      priority: low|medium|high|urgent
      status: open|closed|pending

relationships:
  - { from: Customer, type: OWNS, to: Account }
  - { from: Contract, type: GOVERNS, to: Subscription }
  - { from: Invoice, type: DERIVED_FROM, to: Contract }
  - { from: Ticket, type: REFERENCES, to: Customer }
  - { from: Document, type: ABOUT, to: Product }
```

## Graph Seeding (Cypher Snippets)

```cypher
// 1. Create Constraints
CREATE CONSTRAINT IF NOT EXISTS FOR (c:Customer) REQUIRE c.id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (p:Product) REQUIRE p.id IS UNIQUE;

// 2. Seed Sample Entities
MERGE (c:Customer {id: 'cust_acme', name: 'Acme Corp', workspace_id: 'default_workspace'})
SET c.sensitivity = 'internal';

MERGE (p:Product {id: 'prod_assest_pro', name: 'Assest Pro', workspace_id: 'default_workspace'})
SET p.sensitivity = 'public';

// 3. Seed Relationships
MATCH (c:Customer {id: 'cust_acme'}), (p:Product {id: 'prod_assest_pro'})
MERGE (c)-[:USES]->(p);
```

## SQL Schema Mapping (Postgres)

```sql
-- Semantic Entity Registry
CREATE TABLE IF NOT EXISTS semantic_entities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id TEXT NOT NULL,
    external_id TEXT,
    entity_type TEXT NOT NULL, -- Customer, Product, etc.
    name TEXT NOT NULL,
    properties JSONB DEFAULT '{}',
    sensitivity TEXT DEFAULT 'internal',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_entities_workspace_type ON semantic_entities(workspace_id, entity_type);
```

## Implementation Rules

1. **Colocation**: Keep ingestion logic close to the source connector.
2. **Validation**: Use Pydantic models to validate entities before graph/SQL insertion.
3. **Provenance**: Every entity must link back to a `source_ref` (Document or Episode).

## Suggested Seed Tests

- Ingest a "Customer" from Notion -> Verify `semantic_entities` row and Memgraph node exist.
- Link "Customer" to "Invoice" -> Verify graph edge `OWNS` exists.
- Query for "Acme Corp" -> Verify both Vector (Qdrant) and Graph results are returned.
