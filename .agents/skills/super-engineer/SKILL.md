---
name: super-engineer
description: Architectural governance, Test-Driven AI development (TDD-AI), clean code patterns, and advanced system design principles to ensure production-grade software engineering and zero technical debt.
---

# Super Engineer & Architectural Governance Skill

This skill contains the advanced architectural principles, software design patterns, and AI-collaborative coding guidelines to build production-grade, zero-debt systems. Load this skill whenever you need to design complex features, audit codebase architecture, implement new APIs, or optimize system performance.

---

## 1. The Super Engineer Cognitive Paradigm (The "Director" Pattern)

When collaborating with AI agents, the super engineer shifts from a line-by-line writer to a **Director** who sets clear policies, intent, and machine-enforceable constraints:
1. **Explicit Boundaries**: Never allow agents to make silent assumptions. Define what is strictly out of scope.
2. **Context-Aware Design**: Always inspect existing conventions, hooks, schemas, and directories before writing code. Extend existing utilities rather than recreating them.
3. **Traceability**: All architectural changes must align with the current Phase roadmap and be recorded in [PROGRESS.md](file:///Users/takshvadaliya/Desktop/assert/PROGRESS.md).

---

## 2. Test-Driven AI Development (TDD-AI)

Agents have a tendency to write "plausible-looking" code that references non-existent libraries or uses hallucinated APIs. To prevent this, enforce **TDD-AI**:

1. **Write the Test First**: Before writing any implementation code, write a comprehensive unit or integration test that exercises the expected behavior.
2. **Verify Failure**: Run the test to ensure it fails with a clear, predictable assertion error (e.g. `ModuleNotFoundError`, `AssertionError`).
3. **Write Minimal implementation**: Write the minimum amount of code required to pass the test.
4. **Refactor within Constraints**: Refactor the code to meet quality standards while keeping the test suite green.
5. **No Mocks in Production Code**: Do not mock system components in production files. Mocks are strictly restricted to testing suites.

---

## 3. High-Performance Code Architecture Principles

### A. Strict File Size & Responsibility Limits
* **Maximum File Size**: Keep files between **200-300 lines**. If a file exceeds this range, it must be split by responsibility.
* **Separation of Concerns**: Keep business logic (hooks, models, services) completely separated from presentation logic (components, templates, layouts).
* **Feature Co-location**: Place related files in feature-centric directories rather than splitting them into generic directories (e.g., store backend queries under `/backend/query/` and ingestion tasks under `/backend/ingestion/`).

### B. Defensive Error Handling & Logging
* **Always Try-Except with Context**: Wrap external network calls, file systems, and parsing in robust try-except blocks with specific exception types (never bare `except:`).
* **Fallback Mechanisms**: Always provide sane fallback values or graceful error states rather than letting exceptions crash the application thread (e.g. the 0.8 default score in [evaluators.py](file:///Users/takshvadaliya/Desktop/assert/backend/query/evaluators.py)).
* **Log-Centric Auditing**: Write descriptive debug, info, and error statements to specific logs under `logs/` directory. Include request identifiers or workspace context.

### C. Relational Schema & Database Integrity
* **Explicit Indexing**: Always add `index=True` to relational foreign keys and high-frequency filter query columns.
* **Transaction Deadlock Prevention**: Avoid long-running transactions. Run heavy external operations (such as LLM calls or vector upserts) outside database sessions. Release write locks immediately using `commit()` or explicit connection closures.

---

## 4. Security & Zero-Trust Guidelines

* **Authentication Hygiene**: Never allow unauthenticated requests to fall back to default or mock administrative users in production. Enforce token validation and bubble up `HTTP_401_UNAUTHORIZED` errors.
* **PII & Data Sanitation**: Scrub sensitive records (such as emails, API keys, passwords, and phone numbers) in the Sensory layer before writing them to logs or storing them in vector databases.
* **Secret Storage**: Access credentials only via Pydantic settings or environment variables (`os.getenv`), never hardcoded in source control.

---

## 5. Execution Workflow

When starting a task:
1. **Explore & Verify**: List files and search the repository to locate similar components.
2. **Write Contract/Interface**: Define the type schemas or contract specifications first.
3. **Execute Incrementally**: Complete exactly one task per invocation, commit with conventional commit format, run tests, and stop to review.
