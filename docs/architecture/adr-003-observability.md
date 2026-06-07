# ADR 003 — Observability: Metrics & Tracing

Status: Accepted

Context
-------
We need to trace requests end-to-end across the frontend, backend, LLM providers, and durable orchestrator. Metrics must capture LLM errors and SSE latencies.

Decision
--------
- Use Prometheus for metrics and Langfuse for best-effort tracing.
- Instrumentation points:
  - LLM calls: `assest_llm_calls_total{provider,model,status}` and `assest_llm_call_duration_seconds`
  - SSE streaming: `assest_sse_tokens_total` and `assest_stream_latency_seconds`
  - Attach `request_id` (API/SSE) and `call_id` (LLM invocation) to Langfuse runs/events.
- Langfuse integration is best-effort (no-op when unavailable) via `backend/core/langfuse_wrapper.py`.

Consequences
------------
- Centralized metrics simplify alerting and dashboards.
- Langfuse provides rich per-call context when configured.

Implementation Notes
--------------------
- Files: `backend/core/metrics.py`, `backend/core/langfuse_wrapper.py`, `backend/core/llm_impl.py`, `backend/reasoning/orchestrator.py`.
- Dashboards: Build simple Grafana panels for LLM error rates and SSE latency.
