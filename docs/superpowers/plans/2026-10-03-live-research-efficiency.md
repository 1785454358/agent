# Live Research Shared-Loop Efficiency Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Improve real-web answer quality without increasing research rounds, changing the judge, or adding a summarizer/model stage.

**Architecture:** This independently testable subproject implements the shared-loop portion of the approved specification: bounded initial responsibility, host-validated completion, and a compact model view. Evaluation-entry generalization and SDK telemetry are a separate subproject; existing real-web entry and trajectories remain usable for this validation. Durable evidence, authorization, global assessment and response writing remain unchanged.

**Tech Stack:** Python, Pydantic, LangGraph, pytest-asyncio, existing Gateway and independent Ragas environment.

**Spec:** docs/superpowers/specs/2026-10-03-live-research-efficiency-design.md

## Global Constraints

- Live research: 12 iterations per branch, 40 logical / 80 Provider attempts / 24 Gateway / 360 seconds per run; batch 120 logical / 240 research Provider; scoring 48 Provider.
- Model output 4096; Answer 2000 characters; temperature=0; memory disabled; production default iterations=8 and explicit environment configuration unchanged.
- Fixed original task, user constraints, current authorized IDs and latest whole exchange are pinned. Soft target 8000 estimated input tokens; latest 3 whole exchanges; hard model input budget unchanged.
- No new agent, service, dependency, LLM summarizer, retrieval backend, scoring prompt or gold-answer injection.
- Completion is branch-local, not global coverage. Failed, cancelled, stale or unauthorized evidence cannot be converted into success.
- Preserve existing dirty source edits. Commit only new self-owned documentation; review source deltas without committing unrelated work.
- Referenced execution subskills are unavailable in this session. Execute inline with visible RED/GREEN checkpoints, not an invented subagent review.

## File Map

- `backend/src/deeptrace/harness/research_completion.py`: bounded finish arguments and current raw-support validation.
- `backend/src/deeptrace/harness/agent_tools.py`: register finish, validate ordered local batch, merge observations, emit paired results and completion state.
- `backend/src/deeptrace/harness/agent_state.py`, `policies/execution.py`: persist successful branch summary into outcome/checkpoint.
- `backend/src/deeptrace/strategies/planning.py`, `evidence_evaluation.py`: validate exact query mapping and remap normalized requirement IDs.
- `backend/src/deeptrace/strategies/{plan_execute,workflow,multi_agent}/{nodes,state}.py`: carry initial mapping into branch responsibility; supplements retain precedence.
- `backend/src/deeptrace/harness/{prompts.py,agent_executor.py,policies/agent_context.py}`: optional progress todos, remaining rounds, slim findings and bounded complete-message window.
- `backend/tests/harness/test_finish_research.py`, `test_compact_research_context.py`, `backend/tests/strategies/test_initial_query_targets.py`: behavioral regression tests.

## Task 1: Host-validated same-turn finish

**Interfaces:** `FinishResearchArguments(summary: str)` rejects blank/extra fields; `async validate_completion(*, task, findings, todos, context) -> None` raises bounded `ValueError` codes. `execute_batch` produces `completion_summary` and `stop_reason='completed'` only after validating local preceding effects. `ExecutionPolicy.outcome` consumes the stored summary.

- [x] RED: add a real Gateway two-turn test: turn 1 read authorized evidence; turn 2 record n1, update completed todos and finish. Assert completed at iteration 2, all three paired results, full support/checkpoint and exact summary. Add open-todo, empty/extra summary, no finding, failed preceding record, mixed read/finish, multiple/non-last finish and revoked/stale support cases.

```python
assert result['outcome'].agent_outcome.stop_reason == 'completed'
assert result['outcome'].agent_outcome.iterations == 2
assert result['outcome'].agent_outcome.summary == 'Supported branch conclusion'
assert result['outcome'].research_findings[0].supports[0].quote == body
```

- [x] Run `backend/.venv/Scripts/python.exe -m pytest backend/tests/harness/test_finish_research.py -q` from repository root with `PYTHONPATH=backend/src`; verify missing-finish behavior causes assertion failure, not import/setup error.
- [x] GREEN: add finish schema/tool. Execute finish last only in all-local batches; preceding errors reject it. Revalidate at least one recorded candidate's ACTIVE/version/hash/exact quote against authorized raw source. Existing todos must all be completed. Do not manufacture todos or erase failures. Store summary and all paired observations; stop takes precedence over iteration cap, while fatal/cancel/budget take precedence over finish.
- [x] Run new tests and `backend/tests/harness` before proceeding. Review this task's delta; keep dirty source uncommitted.

## Task 2: Initial responsibility contract

**Interfaces:** `validate_query_targets(payload, queries, proposed, sealed) -> dict[str, list[str]] | None` validates exact normalized keys, unique known IDs, full coverage and synchronized ID renumbering. `seal_initial_plan` produces `query_targets` and a degradation diagnostic. Strategies consume `(supplement_targets or query_targets)[query]` with explicit supplement precedence.

- [x] RED: query a/r4 and b/r3 seal to a/r1 and b/r2. Missing/unknown/omitted mapping must collapse to one full-question branch while retaining both requirements. Add three-mode route/context tests.

```python
queries, sealed = seal_initial_plan('full task', payload, ['a', 'b'])
assert sealed['query_targets'] == {'a': ['r1'], 'b': ['r2']}
assert [r.description for r in sealed['requirements']] == ['first fact', 'second fact']
```

- [x] Run `backend/.venv/Scripts/python.exe -m pytest backend/tests/strategies/test_initial_query_targets.py -q`; inspect expected RED.
- [x] GREEN: require mappings for new plans, add planning JSON instruction, route initial and supplemental responsibilities consistently. Update intentional legacy multi-query test fixtures with explicit mappings; do not weaken their requirement/constraint assertions. Single-query missing mapping also degrades per spec, preserving valid requirements instead of replacing them.
- [x] Run strategy and integration suites. Review delta; do not commit existing dirty files.

## Task 3: Compact model view and remaining rounds

**Interfaces:** `prepare_messages_with_diagnostics(state, tools, budget, *, remaining_iterations=None)` returns complete protocol messages and diagnostics; defaults preserve callers. `RESEARCH_CONTEXT_SOFT_TOKENS=8000`, `RESEARCH_RECENT_GROUPS=3` are identity-visible policy constants. Durable messages, n refs and full finding DTOs are never rewritten.

- [x] RED: create six complete tool exchanges with distinct text; assert only latest three enter model view, old data still in state, tool results remain paired. Assert slim note omits raw quote/hash, fixed task/version conditions remain, assigned and background requirements are distinguished, remaining budget visible, soft oversized latest group stays with a diagnostic and hard overflow raises `ContextLimitError`.

```python
messages, diagnostics = prepare_messages_with_diagnostics(state, (), budget)
assert len([m for m in messages if isinstance(m, ToolMessage)]) == 3
assert state['messages'] == original
assert note.supports[0].quote not in messages[1].content
```

- [x] Run `backend/.venv/Scripts/python.exe -m pytest backend/tests/harness/test_compact_research_context.py -q`; inspect RED.
- [x] GREEN: count bounded groups independently once and final serialized selection exactly; preserve latest group and fixed task, remove older groups/elastic notes as whole units under soft target. Include bounded last query/read/error summary, compact candidate claim/source/ref/confidence, and explicit untrusted labels. Make todo optional and allow authorized-source-first reads; prompt exact find/after contract and last-two-round record/finish behavior. No answer-specific fact insertion.
- [x] Run harness/strategies/integration and full backend tests, Ruff changed files, independent Ragas tests. Review security, protocol, efficiency and compatibility before paid API work.

## Task 4: Once-only real-web validation and honest report

**Interfaces:** existing `deeptrace.eval` live entry consumes the same known diagnostic dataset and caps; independent existing scorer consumes exported records. New source identity/snapshot and new output folders are mandatory; old artifacts remain immutable.

- [x] Read existing preflight/runner/scorer source and flags, register new source snapshot/data/judge identity and limits before any paid invocation. Ensure no `.env` or gold reference enters tools. Existing source hash includes compact policy constants.
- [x] Run three real modes once on `asyncio-live-01`, using original 12-turn/run/batch/model/output controls. Score exported records once with unchanged scorer, maximum 48 scoring Provider attempts. No automatic paid retry, selective mode replacement or scoring rerun.
- [x] Report F1/Faithfulness/Goal, completed/partial reasons, every branch round count, wall time, actual token usage, search Gateway/adapter attempts (billing credits unknown), and source-version/answer-obligation review. Old SDK attempts are inferred rather than directly observed; no invoice-cost conversion.
- [x] If run identities/limits cannot be safely frozen, stop before paid work. If outputs fail full constraints, keep failure artifacts and name the remaining issue; do not mark product accepted based on local finish alone.
- [x] Save validation document and commit only self-owned plan/report documentation after reviewing exact staged paths.

## Self-review

This subproject covers spec sections 1–3 and uses existing section-4 entry for the explicitly authorized three-run diagnostic; section-4 CLI generalization/direct SDK telemetry is intentionally separate and not claimed implemented. No scoring change, budget increase or canonical/Writer repair is bundled. All new interfaces above have behavioral tests; no substitute for a missing human/independent review is claimed.

## Execution evidence (2026-10-03)

Shared-loop tasks and the once-only real-web validation are complete, not the separate CLI/SDK-telemetry subproject. Full backend regression: 1138 passed / 2 deselected; independent Ragas: 34 passed. New three-mode research and scoring ran once under unchanged 12-turn caps. P&E/WF execution completed; MA partial/tool_error. F1 P&E .44, WF .89, MA .57: primary quality target NOT achieved. Full source, protocol, cost, source-version/semantic failures and retained outputs are documented in docs/evaluation/live-efficiency-validation-20261003.md. No production fix was slipped into the frozen paid batch.
