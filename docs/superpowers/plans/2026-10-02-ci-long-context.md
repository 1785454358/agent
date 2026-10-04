# Offline Evaluation CI and Long-Context Diagnosis Implementation Plan

> **For agentic workers:** executing-plans/subagent-driven-development are unavailable; execute the user-approved continuation inline with TDD and code review.

**Goal:** Wire independent offline scorer CI and diagnose evidence delivery through the actual application without changing production selection or paid budgets.

**Architecture:** Keep existing backend image tests, add an isolated scorer image/job using the existing requirements.lock. Dependencies/tokenizer cache may download during setup; test RUN instructions have network=none. Evaluation-only diagnostics compare reference spans with recorded fetched bodies and responder messages after normal application execution, never feed annotations into runtime.

**Tech Stack:** Existing Docker/BuildKit, GitHub Actions, Python/Pydantic/pytest; no new production dependencies.

**Spec:** docs/superpowers/specs/2026-10-01-complete-agent-benchmark-design.md, already approved; master Task 7 and last handoff accepted by user “继续”.

## Constraints

- Preserve all dirty files and old experiment results; no automatic commit or remote CI dispatch.
- No paid API calls or real judge; run diagnostic with ScriptedResearchModel only.
- Development-only default; do not tune after reading held-out test results.
- Report raw-document retention, source selection and prompt visibility separately; literal span visibility is not semantic correctness.
- Do not crop corpus by gold location, enlarge production limits or implement a new retrieval architecture in this slice.
- Docker daemon is unavailable locally; report packaged/remote validation as unverified, not CI passed.

## Task 1 — Offline CI isolation

**Files:** .github/workflows/ci.yml, backend/Dockerfile, backend/evaluation/Dockerfile, .dockerignore, backend/tests/deployment/test_eval_ci.py, backend/evaluation/tests/conftest.py and test_offline_boundary.py.

- [x] Add failing contract checks for an independent scorer build job, no secret wiring, minimal build context and network-isolated test instructions; these are configuration checks, not remote execution proof.
- [x] Add actual HTTP dispatch guard tests for the entire scorer suite, not only its quality test file; observe failure before moving the existing fixture.
- [x] Add scorer Dockerfile with Python 3.12, locked install, explicit file copies, tokenizer warm-up during setup, network-disabled tests and no production project install.
- [x] Backend test stage receives evaluation identity files and warms tokenizer before running pytest with --no-sync and network=none; release stage unchanged.
- [x] Run all local scorer tests and parse/lint CI; attempt only read-only Docker readiness check. No remote dispatch or large image pull.

```python
with pytest.raises(RuntimeError, match="offline_scorer_network_blocked"):
    httpx.Client().get("https://example.org")
```

## Task 2 — Long-document evidence delivery audit

**Files:** backend/src/deeptrace/eval/context_audit.py, backend/tests/eval/test_context_audit.py; docs/evaluation/ci-long-context-20261002.md.

**Interfaces:** analyze_delivery(assets, records) -> dict; CLI --bundle --out --question-id (repeatable, dev IDs only), uses existing run_matrix workflow/baseline and saves raw records plus source/diagnostic identities.

- [x] Test actual normal application with a synthetic long document containing a tail-only marker: storage retains the marker while responder receives only the configured excerpt. Report loss, not false delivery success.
- [x] Test a short source whose marker reaches both storage and responder; missing fetch differs from excerpt loss; unknown task/source and altered bodies refuse analysis.
- [x] Implement scoring-side exact-span auditing of fetched sources and each responder turn. Separate not_fetched, stored_not_selected, selected_not_visible, visible.
- [x] Reject missing model-message traces/artifact errors rather than claiming absence; diagnostics are full-literal-span checks and must disclose their conservative limit.
- [x] CLI accepts only scripted execution, dev split and preselected task IDs. Save manifest-like source/dataset/selection identity before using models; refuse nonempty output.
- [x] Execute representative dev questions selected before outputs: single_hop-dev-01, multi_hop-dev-02, version_boundary-dev-02. Preserve outcomes and all evidence; no quality scores.

```python
assert result["selected_not_visible"] == 1
assert result["visible"] == 0
assert tail_marker in record.evidence[0]["body"]
```

## Task 3 — Review and handoff

- [x] Review correctness, simplicity, isolation, secrets, path bounds and performance; inspect exact truncation source before explaining cause.
- [x] Full project/isolated scorer offline suites, Ruff, config parse and artifact hashes.
- [x] Document diagnostic evidence and local Docker limitation; update master and résumé only with verified engineering facts.
- [x] If diagnosis supports a production excerpt-selector change, propose a bounded query-based design separately for approval. No promise of real quality improvement.

Self-review: follows existing approved workflow and keeps paid calibration separate. Diagnostic references are used only after recording actual execution. CI installation networking is distinguished from test networking. Does not claim an unexecuted GitHub run or judge quality.
