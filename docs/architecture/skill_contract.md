# Assest — Skill Contract Specification

## Purpose

This document defines the formal contract for "Skills" in the Assest ecosystem. A Skill is a reusable capability (e.g., searching knowledge, looking up an invoice, creating a ticket) that can be invoked by an Orchestrator.

Formalizing these contracts ensures that the Planner can reason about inputs/outputs and the State Manager can track execution reliably.

## Skill Envelope (JSON)

Every skill call and response must follow this structured envelope.

### Request Envelope

```json
{
  "skill": "skill_name",
  "version": "1.0",
  "execution_id": "uuid",
  "workspace_id": "uuid",
  "user_id": "uuid",
  "inputs": {
    "param1": "value1"
  },
  "metadata": {
    "idempotency_key": "string",
    "timeout": 30
  }
}
```

### Response Envelope

```json
{
  "status": "success | error",
  "data": {
    "key": "value"
  },
  "error": {
    "code": "string",
    "message": "string"
  },
  "audit": {
    "started_at": "iso-timestamp",
    "completed_at": "iso-timestamp",
    "duration_ms": 123
  }
}
```

## Standard Skills

### `internal_knowledge_search`
- **Inputs**: `query` (string)
- **Outputs**: `answer` (string), `sources` (list of {title, url})

### `invoice_lookup`
- **Inputs**: `invoice_id` (string)
- **Outputs**: `invoice_id`, `status`, `amount`, `currency`, `due_date`

### `ticket_creation`
- **Inputs**: `summary` (string), `description` (string), `priority` (string)
- **Outputs**: `ticket_id`, `status`, `url`

## Idempotency Expectations

- Action skills (like `ticket_creation`) **must** support idempotency via `idempotency_key`.
- Retrieval skills (like `invoice_lookup`) should be read-only and side-effect free.

## Audit Logging

Every skill implementation must log:
1. `skill.call_start`: {skill, execution_id, inputs}
2. `skill.call_end`: {skill, execution_id, status, duration_ms}
