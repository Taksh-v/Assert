# Skill Contract - MVP

Purpose: define a minimal contract for skills (connectors/tools) so the orchestrator can call them reliably.

Contract elements:
- name: unique skill identifier
- input_schema: JSON Schema describing inputs
- output_schema: JSON Schema describing outputs
- idempotent: boolean flag; if true skill calls with same `idempotency_key` must be safe to re-run
- timeout_seconds: suggested execution timeout
- error_modes: enum [retryable, fatal, user_action_required]

Example usage:
 - Orchestrator constructs a `SkillCall` payload with `idempotency_key`, `params`, and `meta`.
 - Connector wrapper validates `params` against `input_schema`, enforces idempotency, logs audit record, and returns typed output matching `output_schema`.
