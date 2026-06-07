# ADR 001 — LLM Routing & Resilience

Status: Accepted

Context
-------
The system must call external LLM providers (OpenRouter, Groq, local LiteLLM proxy) reliably. Different providers expose different model ids and may intermittently fail (404, rate limits, network errors). Tests and production showed frequent provider-specific failures leading to silent SSE UI.

Decision
--------
Centralize LLM routing behind `SharedLLMClient` with the following policy:

- Resolve provider from configuration (`openrouter_api_key`, `groq_api_key`, `litellm_proxy_url`).
- Normalize configured model names per provider.
- Maintain a `FallbackPolicy` containing a primary model plus ordered fallbacks.
- Attempt models in order with exponential backoff and limited retries (configurable via `openrouter_retry_attempts` and `openrouter_retry_backoff_base`).
- Use a `CircuitBreaker` per provider to stop requesting repeatedly on persistent failures.
- Emit structured logs and metrics (provider, model, call_id, duration, status) and attach `call_id` to Langfuse events.

Consequences
------------
- Improves resilience by trying alternative models automatically.
- Simplifies troubleshooting by centralizing metrics and logs.
- Adds a tiny increase in latency when fallbacks are attempted.

Implementation Notes
--------------------
- File: `backend/core/llm_impl.py` — `SharedLLMClient`, `FallbackPolicy`, `CircuitBreaker`.
- Config: `backend/core/config.py` provides retry/backoff and fallback list settings.
- Tests: `tests/unit/test_llm_fallback.py` and `tests/unit/test_llm_retry_backoff.py`.

Review
------
Re-evaluate fallback lists periodically and audit provider account model access to avoid unnecessary fallbacks.
