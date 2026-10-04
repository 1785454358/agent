# Global Support Budget Implementation Plan

> **For agentic workers:** Execute inline with TDD; executing-plans/subagent-driven-development are unavailable in this session. No new threads are needed.

**Goal:** Preserve every valid support when its raw-text union fits the existing source budget, then verify all three modes with real APIs.

**Architecture:** Keep `supported_ranges(record, body, supports, limit)` canonical for Writer and live evaluator. Validate and deduplicate, reserve merged necessary ranges globally, greedily select whole quotes only on genuine overflow, then expand optional context using merged-union cost. No routing, prompts, relevance, gates, model, budgets or scoring changes.

**Tech stack:** Python, pytest, existing LangGraph nodes, isolated Ragas 0.4.3.

**Approved spec:** `docs/superpowers/specs/2026-10-03-global-support-budget-design.md`.

## Task 1: Reproduce and repair the shared allocator

- [x] Add failing tests in `backend/tests/tools/test_support_budget.py`: cores 100:500 and 1000:1400 must both fit exactly in 800; overlapping 100:500 and 400:650 with limit 700 must yield 25:725. Test order permutations, duplicates, adjacency, clipped margins, malformed support and strict integer limits; true overflow retains complete early quotes and tries later smaller quotes.
- [x] Add `backend/tests/integration/test_support_budget_consumers.py`: six disjoint 500-character quotes must survive actual three-mode evaluation; Answer and Report preserve all accepted findings for completed v2/v3 consumers. True character/token overflow still remains partial.
- [x] Run these tests against the old implementation and record assertion failures, not import errors.
- [x] Implement only `backend/src/deeptrace/tools/evidence_views.py`: validate limit; stable dedup of validated coordinates; merge all cores before cost; on overflow merge each whole candidate and accept only if union fits. Expand frozen merged cores in coordinate order, binary-search largest margin 0..120 whose clipped merged union fits. Keep inputs unmodified.
- [x] Run focused tests, recover previous real multi-hop P&E supports from frozen artifacts, and verify every old accepted support fits the new view. This is offline replay, not new quality evidence.

## Task 2: Review, offline acceptance and freeze

- [x] Run `backend/.venv/Scripts/python.exe -m pytest -m "not real"` from backend; isolated `.venv-ragas/Scripts/python.exe -m pytest evaluation/tests`; Ruff for changed production/tests.
- [x] Five-axis self-review: correctness/boundaries, readable two-phase allocation, canonical shared API, unchanged support/security checks, bounded deterministic cost. No new dependencies.
- [x] Create `docs/evaluation/support-budget-validation-20261003.md` preregistration. Verify prior manifest fields and scorer identity, three output dirs absent. Capture source identity, HEAD, production and added test snapshots before paid execution. Do not edit frozen source during execution.

## Task 3: Once-only real verification

All commands below run from backend. Use the existing frozen dev corpus, not live web. Keep every partial/failed/NA result, no rejudging, no old artifact changes, no new baseline. Strict comparison has n=0 baseline pairs and null delta/CI. Same-model judge, three known dev cases, one repeat and no independent human review limit conclusions.

```powershell
.venv/Scripts/python.exe -X utf8 -m deeptrace.eval --model real --modes plan_execute,workflow,multi_agent --repeats 1 --response-mode answer --response-max-chars 2000 --max-model-calls 40 --max-tool-calls 24 --max-provider-attempts 80 --max-batch-model-calls 360 --max-batch-provider-attempts 720 --agent-iterations 12 --max-output-tokens 4096 --run-timeout 360 --dataset ../tmp/evidence-loop-real-20261002-assets/questions.jsonl --corpus ../tmp/evidence-loop-real-20261002-assets/corpus.jsonl --run-prefix support-budget-real-answer-20261003 --out ../tmp/support-budget-real-answer-20261003
.venv-ragas/Scripts/python.exe -X utf8 evaluation/ragas_quality.py --input ../tmp/support-budget-real-answer-20261003/quality_eval.json --out ../tmp/support-budget-real-answer-quality-20261003 --max-provider-attempts 144 --env-file .env
.venv/Scripts/python.exe -X utf8 -m deeptrace.eval.compare_cli --input ../tmp/support-budget-real-answer-20261003/quality_eval.json --scores ../tmp/support-budget-real-answer-quality-20261003/quality_scores.json --metadata ../tmp/evidence-loop-real-20261002-assets/analysis-card.json --out ../tmp/support-budget-real-answer-comparison-20261003
```

- [x] Research once (9 runs), native scoring once, strict compare once. Poll sessions and communicate at least every 60 seconds; exit 1 with partial records is not justification for retry.
- [x] Audit full records, final actual visibility, source coordinates/hash, support delivery, status and Writer causes, evaluator valid coverage, logical/Provider/tool calls and token usage. Capture all errors and NA reasons, cost unknown unless priced.
- [x] Report primary P&E F1/Faithfulness/Goal and each mode's complete coverage; descriptive prior-batch contrast only. Preserve misses and production-web limitation. Update plan and report with exact observed results.
