# Unified Run Result Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Preserve authoritative Harness completion and research metadata in Local and Worker outputs.

**Architecture:** Application service returns one typed ApplicationRunResult with response, optional research and metadata-only citation sources. Adapters map this result without reinterpreting completion or querying evidence again.

**Tech Stack:** Python, Pydantic, LangGraph, pytest, existing EvidenceStore adapters.

**Spec:** ../specs/2026-10-01-run-result-standardization-design.md

## Global Constraints

- No database schema, dependency or production configuration changes.
- Preserve existing user edits, especially citations and untracked evaluation code.
- Steps are research execution steps, not model calls or token usage.
- Real smoke: one public question, temporary SQLite/lexical storage, 3 agent iterations, 1024 output tokens, 180 seconds, 12 logical model and tool calls each.
- No unavailable execution subskills/subagents are installed; execute inline in this already authorized session, with TDD checkpoints.

### Task 1: Application result boundary

**Files:** Create `backend/src/deeptrace/application/result.py`; modify `backend/src/deeptrace/application/research.py`; test `backend/tests/application/test_research_service.py`.

**Interfaces:** `ResearchApplicationService.invoke(request, *, config, context) -> ApplicationRunResult`; fields: run_id, thread_id, status, response_outcome, research_outcome, termination_reason, executed_steps, unresolved_gaps, sources.

- [x] Add regression using a graph boundary returning a valid cited response and research max_iterations/7 steps; use real InMemoryEvidenceStore. Assert `result.status == "partial"`, `result.termination_reason == "max_iterations"`, `result.executed_steps == 7`, retained gaps and sources.
- [x] Run `.venv/Scripts/python.exe -m pytest tests/application/test_research_service.py -q` from backend; observe failure on absent result metadata, not missing imports.
- [x] Implement Pydantic contract, reject nonterminal status, validate ResponseOutcome/ResearchOutcome, resolve cited metadata once. Cause selection:

```python
reason = research.termination_reason if research and research.termination_reason != "completed" else response.partial_reason
reason = reason or ("completed" if status == "completed" else "partial")
```

- [x] Cover no research/no citations, invalid status, missing/cross-workspace sources and independent gap lists; rerun focused tests.

### Task 2: Adapters and consumers

**Files:** Modify `application/agent_adapter.py`, `runtime/local.py`, `cli.py`; modify service consumers under tests/harness, tests/integration, tests/runtime; create `tests/application/test_agent_adapter.py`.

**Interfaces:** Adapters consume Task 1 result; preserve existing AgentResult and RunRecord output contracts and lifecycle behavior.

- [x] Add regressions for both adapters returning partial despite usable response; assert reason, gaps, sources and Worker steps7. Run focused tests before editing adapters.
- [x] Map `answer=result.response_outcome.content`, `status=result.status`, `termination_reason=result.termination_reason`, `sources=result.sources`, gaps and Worker steps. Delete duplicate evidence reads. Completion event text uses overall status.
- [x] Explicitly migrate service consumers to `result.response_outcome`; leave response-subgraph consumers unchanged. CLI label becomes 执行步数.
- [x] Run `.venv/Scripts/python.exe -m pytest tests/application tests/runtime/test_local.py tests/harness/test_workflow_response_slice.py tests/integration -q -m "not real"`; preserve resume/continuation and thread identity behavior.

### Task 3: Bounded verification and handoff

**Files:** Modify `tests/real/test_real_smoke.py`; create `docs/architecture/2026-10-01-run-result-verification.md`.

**Interfaces:** Test wrappers implement `invoke`/`execute` and forward to actual gateways; limits apply before external calls.

- [x] Replace real smoke output assertions with unified result/snapshot consistency assertions. Use dataclasses.replace for lexical, local, empty MySQL DSN and bounded settings; unique IDs and tmp_path; close bundle in finally.
- [x] Run `.venv/Scripts/python.exe -m pytest -q -m "not real"`, Ruff changed source / tests I,F, formatter and `git diff --check`.
- [x] Run `.venv/Scripts/python.exe -m pytest tests/real/test_real_smoke.py -q -m real`; record actual result, do not rerun whole evaluation on service failure.
- [x] Self-review changes, record limitations (no real usage metrics, no broad quality benchmark), stage only task files and commit.

## Self-review

Spec covers status/reason/sources, adapters, all invocation branches and bounded real verification. Evaluation enhancement is a separate design; this plan does not change user evaluation work or introduce SaaS requirements.
