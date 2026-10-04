# Benchmark Continuation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans if available; neither it nor subagent-driven-development is listed here. Continue inline using TDD and five-axis review.

**Goal:** Make response length explicit, produce auditable paired comparisons, and run isolated multi-turn memory lifecycle evaluations.

**Architecture:** Extend the existing approved file-based evaluation workflow. Normal application graphs remain authoritative; memory exercises temporary SQLite through the normal application; analysis consumes frozen results without rerunning Agents or judges.

**Tech Stack:** Current Python/Pydantic/LangGraph/SQLAlchemy, standard-library paired percentile bootstrap; pinned isolated Ragas unchanged.

**Spec:** `docs/superpowers/specs/2026-10-01-complete-agent-benchmark-design.md` (already user-approved), implementation plan `2026-10-01-complete-agent-benchmark.md`.

## Global constraints

- Preserve original real-pilot records, failures, scores and source snapshot.
- No additional real requests in this slice: the user selected one pair, not another matrix; numerical unspent request capacity alone is not a new experiment authorization.
- Never label scripted application exercises as real-model quality or lexical memory as semantic memory.
- No new services/dependencies, no production databases or real user memory.
- Reference/expected fields stay scoring-side. Distinguish application state, retrieval and answer quality.
- Preserve pre-existing dirty and untracked user files; do not partially commit an eval package absent from HEAD.

## Task 1 — Response length contract

**Files:** harness/context.py, responses/graph.py; eval/env.py, runner.py, experiment.py, __main__.py; tests/responses/test_output_budget.py, tests/eval/test_experiment_cli.py.

**Interface:** optional `HarnessContext.response_max_content_chars`; `run_matrix(..., response_max_content_chars=None)`; CLI `--response-max-chars`, recorded in manifest. Explicit constraint is capped by the selected response policy. Unconfigured callers retain existing character limits. Both initial generation and the one correction use the same bound; no arbitrary automatic token-to-character claim.

- [x] Write failing graph tests: REPORT with bound 600 must produce a complete parsed cited answer with a length-sensitive external model; initial unconstrained prompt triggers the original truncated JSON fixture.
- [x] Write failing invalid-bound preflight tests, manifest identity and same-cap baseline/Harness tests.
- [x] Implement minimal typed context field, effective response policy and initial pinned length instruction; plumb explicit optional cap through eval only.
- [x] Verify `pytest tests/responses tests/eval`; review compatibility and do not repair malformed JSON by appending invented text.

```python
assert result["outcome"].partial_reason is None
assert len(result["outcome"].content) <= 600
assert result["outcome"].content.endswith("[1]。")
```

## Task 2 — Paired comparison artifact

**Files:** eval/comparison.py; eval/compare_cli.py; tests/eval/test_comparison.py.

**Interface:** `compare_records(records, score_rows, *, metadata, seed=0, resamples=2000) -> dict`; metadata explicitly identifies dataset/split per question. Reject duplicate run IDs/repeats, unknown judge rows and invalid finite/range scores. Coverage counts all attempted records; completed-only and all-output summaries remain separate.

- [x] Failing tests with hand-derived repeated scores: aggregate within each question before pairing, not by run; keep failures in denominators; never mix dataset/split; missing/error are null, not zero.
- [x] Test deterministic question-level paired percentile bootstrap; zero/one pair => null interval; missing scores on some repeats exclude that task from the primary quality pair and disclose counts (no survivor-biased complete pairing).
- [x] Implement standard-library resampling of task differences, per-system categorical means, latency quantiles and per-system failure breakdown. Keep each Ragas metric separate, no weighted total.
- [x] CLI reads JSON v2 and exact associated quality identity, attaches explicit data card, writes JSON and Markdown without touching old artifacts.
- [x] Apply it to the old real pilot (no network) and preserve the original benchmark verdict.

```python
assert summary["paired_tasks"] == 1
assert summary["difference"] == 0.5
assert summary["interval_95"] is None
```

## Task 3 — Memory lifecycle episodes

**Files:** eval/memory_runner.py, eval/data/memory/lifecycle-v1.json, tests/eval/test_memory_runner.py.

**Interface:** `run_memory_episode(episode, *, enabled, model_factory, limits) -> dict` uses one temporary SQLite database, a controlled UTC clock, isolated user/workspace identities, a fresh application thread per recall probe, and shared logical/tool counters across all episode stages. This slice is scripted-only with zero Provider attempts; real memory calibration and its shared Provider ledger remain future work. Observations include stored versions/status, actually recalled memory IDs and model messages; expected content is not injected into graph inputs.

- [x] Read existing normal memory write/recall/delete and application request tests; exercise real store, application and harness, controlling only the external model.
- [x] Failing tests for on/off cross-thread recall, version replacement, deletion, expiry, namespace isolation and current-request priority visibility.
- [x] Implement six categories × two controlled episodes, two on/off variants each. Lifecycle actions use actual remember / store status APIs and normal explicit application writes; no fake semantic retrieval backend.
- [x] Persist one full episode at a time using existing ExperimentStore and atomic JSON; cancelled episodes remain claimed/ambiguous. CLI is scripted-only in this slice and records `controlled_scenario`, `sqlite_lexical`, `scripted` separately.
- [x] Run the 24 scripted episode variants, produce per-probe checks and violations; no judge/API and no invented answer-quality score.

```python
assert result["cross_namespace_hits"] == 0
assert result["memory_backend"] == "sqlite_lexical"
assert result["turns"][-1]["prior_messages"] == []
```

## Task 4 — Review and verification

- [x] Review each slice for correctness, module boundaries, credential leakage and workload bounds; no test-only switch in production classes.
- [x] Full offline project suite, pinned scorer suite and Ruff on changed sources.
- [x] Report exact results and diagnosed root cause; update old report with a correction note, not rewritten raw data or fabricated improved metrics.
- [x] Update the master plan only for completed items. Full 30-question dataset, public subset, semantic memory, human blind review and further real calibration remain separately visible.

Self-review: this is a continuation of the approved scope, not a new platform. Response length and retrieval coverage are distinct causes. Statistical analysis is offline; memory contracts do not demonstrate real-model preference compliance.

Execution: 670 offline project tests passed / 2 real deselected; 28 isolated scorer tests passed. Formal 24 scripted variants: on 7/7 targets, off 0/7, zero contract violations or cross-namespace hits. Resume preserved result bytes. 153 source/data/dependency snapshot files hash-verified. Review-driven RED tests caught malformed metric boundaries, exact judged-input mismatch and enabled-memory write failure being incorrectly accepted. All addressed. No new Provider calls. The earlier Store-loss inference was corrected using full tool traces; retrieval coverage itself remains unfixed.
