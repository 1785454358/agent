# Governed Benchmark Assets Implementation Plan

> **For agentic workers:** Use executing-plans/subagent-driven-development only if available; neither is listed in this session. Execute the approved continuation inline with TDD and code review.

**Goal:** Freeze 30 source-verified research questions with 12 dev / 18 test split, provide runtime-safe projections and import five public tasks without running paid APIs.

**Architecture:** One strict benchmark bundle holds scoring-side references and provenance. A loader validates pinned licensed raw documents and returns existing EvalQuestion/Corpus shapes; source annotations never enter retrieval. CLI opts into a bundle and split; old smoke and pilot formats remain unchanged.

**Tech Stack:** Existing Pydantic, Python standard library, pytest; existing isolated Ragas unchanged.

**Spec:** docs/superpowers/specs/2026-10-01-complete-agent-benchmark-design.md, approved by the user before implementation; master plan Task 4 / Task 7.

## Global constraints

- Six categories × five questions; two dev and three test per category. Same upstream document group cannot cross splits; related framework concepts still overlap and must be disclosed.
- Source groups and question IDs frozen before Agent output. Public tasks selected before viewing their reference/test outputs.
- Download only public primary-source text after checking upstream license; preserve verbatim raw files, commit, path, full-content hash, retrieval UTC and license notice.
- Verify each reference claim against literal source spans; insufficiency references describe the absent information rather than inventing facts. Source verification is agent review, not human gold.
- No additional paid API requests, no new runtime services/dependencies, no production databases or private data. Old results/snapshots remain untouched.
- Do not commit an incomplete subset of the pre-existing untracked eval tree. New governed assets change future source identity; old experiment identities intentionally cannot resume with new source.

## Task 1 — Strict scoring-side bundle and runtime projection

**Files:** backend/src/deeptrace/eval/assets.py; backend/tests/eval/test_assets.py.

**Interfaces:** `load_benchmark(path: Path, *, split: str) -> BenchmarkAssets`; `.questions` projects to EvalQuestion, `.corpus` to existing Corpus, `.analysis_card()` emits exact selected dataset/corpus hashes and metadata for compare_cli. Immutable strict Pydantic source/task/reference models validate before invocation. `python -m deeptrace.eval.assets --bundle PATH --out DIR` validates all splits and writes audit/cards, no Agent.

- [x] Write failing tests for reference/provenance leakage, changed raw bytes, quote mismatch, escaping source paths, duplicate IDs, source-group split leakage and category/split counts.
- [x] Observe RED with missing loader, implement source SHA-256 + exact contiguous-span checks, explicit source group and reference separation. Bound bundle/source sizes and counts.
- [x] Test hand-checked projected body equality; reject injected annotation keys and reference facts in runtime inputs, without excluding legitimate facts already in public documents.

```python
assets = load_benchmark(bundle, split="dev")
assert assets.questions[0].question == "How is state saved?"
assert assets.corpus.documents()[0].body == "Checkpoints save graph state."
assert "gold_canary" not in str(assets.corpus.documents())
```

## Task 2 — CLI preflight and baseline gold-invariance

**Files:** eval/__main__.py; tests/eval/test_experiment_cli.py; tests/eval/test_baseline.py.

- [x] Failing test: corrupted bundle rejects before model factory/output creation; opt-in `--benchmark` / `--split` keep smoke backward-compatible.
- [x] Reject mixing bundle with explicit legacy dataset/corpus; add bundle identity/split to manifest, attach provenance and source-review counts to quality-ready export.
- [x] Run same real application baseline with two different scoring references; actual output and model/tool inputs must be identical.

```python
assert baseline_a.answer == baseline_b.answer
assert baseline_a.trajectory == baseline_b.trajectory
```

## Task 3 — Licensed primary-source research assets

**Files:** eval/data/benchmarks/research-v1/bundle.json, upstream/*.mdx, LICENSE.txt; docs/evaluation/governed-assets-20261002.md.

- [x] Pin LangChain official docs commit, confirm MIT notice; choose disjoint LangGraph-runtime vs LangChain-agent source groups, download unmodified raw text.
- [x] Draft 30 meaningful questions across the six categories; verify each positive reference against source line ranges and exact span text, label absence boundaries for insufficient-evidence tasks.
- [x] Freeze 12/18 lists, save category counts/review provenance, validate both projections and analysis cards offline. No claims of hidden human review, current-latest guidance or semantic/general-topic holdout.

## Task 4 — Public subset import and honest boundary

**Files:** eval/data/public/drb-v1/selection.json, upstream LICENSE/query.jsonl, importer in assets.py only if shared validation earns reuse, focused tests.

- [x] Check official DRB upstream license and pinned query file before downloading answer/reference files (do not read model outputs).
- [x] Deterministically select first five technology/engineering tasks by ID after excluding private, unsafe/professional or unavailable specialized-tool requirements; retain original text/IDs and selection/exclusion reasons.
- [x] No upstream reference means factual metric N/A; public tasks are not wired to the frozen local-corpus runner or called official RACE/FACT. Live-web execution remains explicitly unimplemented until its separate adapter/budget is ready.

## Task 5 — Review, verification and handoff

- [x] Review correctness, simplicity, architecture, path/license/credential boundaries and bounded work; perform source checks independently of loader assertions.
- [x] Full project offline suite and independent scorer suite, Ruff and artifact/hash checks. Generate source audit and runtime projections, not scripted answer-quality scores.
- [x] Update master progress and résumé wording only for completed asset governance. Human review, live public execution, new real calibration and complete matrix remain incomplete.

Self-review: approved scope retained, no new platform or dependence on paid calls. Exact-span validation supports reproducibility, not automatic proof of entailment or absence. Raw MDX may contain language alternatives/imported snippet references; limitations are documented and each reference must be grounded in local literal content.
