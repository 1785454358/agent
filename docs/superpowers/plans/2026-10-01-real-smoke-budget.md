# Real Smoke Budget Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Complete one real search/fetch/model/cited-answer run without exhausting an artificially small smoke budget.

**Architecture:** Change only test-time settings and bounded wrappers; preserve actual Harness completion and citation assertions. The user explicitly requested raising the budget and rerunning after the documented 3-round failure. No production defaults or architecture changes.

**Tech Stack:** Existing pytest real test, Settings dataclass, real Harness assembly, temporary SQLite and lexical memory.

**Spec:** ../specs/2026-10-01-run-result-standardization-design.md, real-API verification section; user-approved budget amendment on 2026-10-01 below.

## Global Constraints

- One public technical question per attempt; unique run/thread identity and temporary storage.
- First bounded attempt: per-branch iterations 3 → 6; shared logical limits model 12 → 32, tool 12 → 24; overall timeout 180 → 240 seconds. Output cap 1024. Result: partial/insufficient_evidence, 4 cited sources, iteration_limit and evaluation_unavailable; 21 model/7 tool calls. A single evaluator-only probe hit a connection error and did not establish a truncation cause.
- Second bounded attempt: per-branch iterations 8, output cap 2048; retain global 32 model/24 tool calls and 240 seconds. Capture evaluator finish reason/schema errors and actual tool success. Do not claim truncation without evidence. Transport retries unchanged; no dollar-cost assertion without measured tokens/prices.
- Second attempt result: evaluator schema valid, sufficient=true; two branches completed, one iteration_limit with 3/4 todos complete and only summary remaining. 26 model/9 tool calls, six successful fetches. This concrete remaining blocker justifies a final bounded calibration attempt: 12 rounds per branch, 40 model/24 tool calls, 2048 output tokens and 240 seconds. Do not run a fourth full attempt if this fails; discuss plan-maintenance efficiency instead.
- Preserve status/snapshot/reason/steps/gaps assertions; require completed and valid cited sources, not merely nonempty answer. Record successful search/fetch separately from attempts.
- No production settings, .env, dependencies, user evaluation/citation edits or historical data modifications.
- Subagent-driven-development/executing-plans are unavailable; execute inline using the available debugging/TDD skills.

### Task 1: Raise bounded smoke budget and verify

**Files:** `backend/tests/real/test_real_smoke.py`, `docs/architecture/2026-10-01-run-result-verification.md`.

**Interfaces:** BoundedModel.invoke and BoundedTools.execute forward to real gateways; only test-time limits change.

- [x] RED evidence already observed: previous real test failed with no sources; checkpoints show three 3-round branches exiting before fetch_page. Do not spend another API call reproducing that unchanged failure.
- [x] Change test settings and guards:

```python
agent_max_iterations=6
# Model wrapper rejects calls after 32; tool wrapper rejects calls after 24.
# async with asyncio.timeout(240)
assert outcome.status == "completed"
assert outcome.termination_reason == "completed"
```

- [x] Run from backend: `.venv/Scripts/python.exe -m pytest tests/real/test_real_smoke.py -q -s -m real --tb=short --show-capture=no`; inspect summary and persisted checkpoints if it fails. The two preceding attempts exposed specific blockers; the third is the final budget calibration, not a repeated unchanged test. Larger redesign requires separate discussion.
- [x] Run Ruff I/F and format on the changed test, then full non-real pytest regression. Record actual result (including any failed attempts), limits, successful fetches, sources and timing.
- [x] Self-review and commit only test and task documentation.

Verification outcome: budget calibration executed; all research branches completed in the final attempt, but end-to-end smoke still FAILED due to evaluator string_type validation. Record failure, not goal completion. Proposed production fix requires review of ../specs/2026-10-01-workflow-evaluation-contract-design.md.
