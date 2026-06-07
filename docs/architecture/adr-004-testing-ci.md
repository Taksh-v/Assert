# ADR 004 — Testing and CI for Streaming & LLM Resilience

Status: Proposed

Context
-------
Streaming behavior and LLM fallbacks are sensitive to timing and network errors; unit tests alone are insufficient. CI should run integration tests that exercise SSE and a mock LLM proxy.

Decision
--------
- Keep unit tests for logic and add `tests/e2e` that run a lightweight mock LiteLLM proxy and exercise FastAPI SSE endpoints.
- CI workflow runs: lint, unit tests, and e2e tests in a separate job that optionally runs the mock proxy in-process.
- Add pre-commit hooks: `black`, `ruff`, and `detect-secrets` to catch regressions early.

Consequences
------------
- Slightly longer CI times for e2e runs; but reduces production regressions.

Implementation Notes
--------------------
- Files: `tests/e2e/*`, `.github/workflows/ci.yml` (skeleton), `pyproject.toml` or `requirements.txt` for test dependencies.
