# Complete Agent Benchmark Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立真实资料与公开任务评测、基线和记忆对照、可审计结果及真实实验报告。

**Architecture:** 沿用生产环境的 eval runner，独立 Ragas 环境通过版本化 JSON 评分。实验身份、原始记录与评分各自独立；本地文件管理实验，不增加服务。预算在实际请求之前扣减，未知费用和不完整运行显式留样。

**Tech Stack:** Python 3.12、现有 Pydantic/LangGraph/ToolGateway、标准库、本项目已隔离的 Ragas 0.4.3。

**Spec:** [完整设计](../specs/2026-10-01-complete-agent-benchmark-design.md)。用户已审阅并要求“开始”。

## Global Constraints

- 30 道研究题（12 开发、18 测试）、5 道公开任务、12 个记忆 episode；数据类型分开报告。
- 生产 SDK 不降级；不增加平台服务；真实网络调用显式启用并设置批次限额。
- 工具请求不等于执行成功，completed 不等于任务答对；参考字段不能进入 Agent。
- 原始失败与评审错误留样，未测为 null；简历仅引用实际测量。
- 保护已有未提交文件，不能整体提交用户的 untracked eval 资产。
- 每个任务按 RED → GREEN → review 验证；不同数据或模型身份不能原地续跑。
- 执行技能 executing-plans/subagent-driven-development 未列入本会话可用技能；按用户“开始”要求在当前会话逐项执行，使用可用 TDD 与 code-review-and-quality，不假称已调用缺失技能。

## Files and Boundaries

- `backend/src/deeptrace/eval/experiment.py`：严格实验配置、资产/源码哈希、去凭据模型身份。
- `backend/src/deeptrace/eval/artifacts.py`：身份锁定、原子写入、逐运行记录、重复/损坏/中断拒绝。
- `backend/src/deeptrace/eval/telemetry.py`：请求限额、Provider 尝试记录、usage 完整性；不存认证响应。
- 修改现有 `runner.py / env.py / real.py / __main__.py`：接入上述接口，保留工具导出 v1。
- `baseline.py`：真实的固定搜索/抓取/回答，不读取 gold。
- `assets.py` 和 JSONL/data card：真实来源许可与任务治理；原 smoke 不变。
- 独立环境 `ragas_quality.py`：质量适配、请求预算、评分缓存；不 import deeptrace。
- `memory_runner.py`：多轮、临时 SQLite、时钟与 namespace、on/off。
- `comparison.py`：配对分析与报告；不混入 legacy_custom 均值。
- 对应 `backend/tests/eval/test_*.py` 与 `backend/evaluation/tests/test_*.py`。

## Task 1: Durable experiment identity and records

**Files:** Create experiment.py, artifacts.py; create tests/eval/test_experiment.py, test_artifacts.py.

**Interfaces:** `EvaluationLimits` 为不可变严格配置；`build_manifest(questions, corpus, *, model, modes, repeats, run_prefix, limits) -> dict`；`ExperimentStore(path, manifest, *, resume=False)` 是同步上下文管理器；`load(run_id) -> dict | None`、`claim(run_id)`、`save(record)`。

- [x] Write tests for config change rejection, reordered assets, source hashes, provider credentials removal, positive limits, complete JSON, corruption, partial writes, single writer and failure preservation.

```python
def test_resume_rejects_changed_identity(tmp_path):
    with ExperimentStore(tmp_path, {"schema_version": 2, "model": "a"}):
        pass
    with pytest.raises(ValueError, match="identity"):
        with ExperimentStore(tmp_path, {"schema_version": 2, "model": "b"}, resume=True):
            pass
```

- [x] Run `.venv/Scripts/python.exe -m pytest tests/eval/test_experiment.py tests/eval/test_artifacts.py -q`; observe missing functionality.
- [x] Implement canonical SHA-256 identity excluding volatile start timestamp. Source identity hashes eval, application, Harness, strategies, responses, tools, domain, config, persistence and dependency config; include relative paths, not credentials. Atomic write: unique temporary file, flush/fsync, `os.replace`, cleanup only own temporary file.

```python
encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, allow_nan=False).encode()
with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as handle:
    handle.write(encoded)
    handle.flush()
    os.fsync(handle.fileno())
os.replace(handle.name, target)
```

- [x] Store record hash plus run ID; filenames use run-ID hash, not unchecked path strings. Persist an in-flight claim before work; unfinished claims refuse automatic rerun. Refuse non-resume overwrite or mismatched identity. Reject concurrent writers before requests.
- [x] Rerun tests, review data-loss/path boundaries and document limitations of crash recovery.
- [ ] Commit a coherent owned implementation after resolving the pre-existing untracked eval package boundary; current code is preserved in the workspace, not partially committed as a broken checkout.

## Task 2: Request budgets and usage capture

**Files:** Create telemetry.py, tests/eval/test_telemetry.py; modify real.py and env.py.

**Interfaces:** `RequestCounter(limit, *, used=0).reserve()`; `ModelTelemetry` records provider attempts and successful usage; `MeteredChatModel(inner, telemetry, run_counter, batch_counter)` supports `bind_tools`, `bind`, `ainvoke` with shared accounting. CountingModelGateway receives optional run/batch logical counters and exposes `usage` snapshot.

- [x] Tests cover parallel reservations, transient attempts, bindings sharing one ledger, cancellation, missing/malformed usage and transport failures. Use controlled fake external model but actual ChatModelGateway retries and real counters.

```python
async def test_attempt_limit_applies_to_transport_retries():
    raw = TransientThenSuccessModel()
    meter = ModelTelemetry()
    wrapped = MeteredChatModel(raw, meter, RequestCounter(1), RequestCounter(3))
    gateway = ChatModelGateway(wrapped, retry_attempts=2, retry_base_seconds=0)
    with pytest.raises(ModelCallError):
        await gateway.invoke(role="writer", messages=valid_messages())
    assert meter.snapshot()["provider_attempts"] == 1
```

- [x] Run focused test before implementation. Reserve run and batch counters together without yielding; over-limit call never touches the external model, failed/ambiguous calls remain consumed.
- [x] Observe `AIMessage.usage_metadata` input/output counts; expose observed subtotals and missing attempt counts, aggregate actual tokens only if every attempted response has complete usage. Do not persist raw response metadata or exception text. SDK internal retries remain zero.
- [x] Pass tests and review counter concurrency and bindings; production gateway behavior unchanged outside evaluation.

## Task 3: Runner and CLI integration

**Files:** Modify runner.py, env.py, real.py, __main__.py; create tests/eval/test_experiment_runner.py, test_experiment_cli.py; create docs/evaluation/experiment-records.md.

**Interfaces:** `run_matrix(..., limits=None, store=None, batch_model_counter=None)` retains existing callers; RunRecord adds complete evidence and usage. CLI adds `--resume`, `--max-model-calls`, `--max-tool-calls`, `--max-provider-attempts`, `--max-batch-model-calls`, `--max-batch-provider-attempts`, `--run-timeout`, `--agent-iterations`.

- [x] Write tests asserting long answer is intact, evidence body equals fetched corpus, each run is saved before next run, resumed completed/failed samples are not called again, identity mismatch fails before factory invocation, cancellation leaves ambiguous claim, and exhausted counters stop requests.

```python
records = await run_matrix(questions, corpus, model_factory=LongAnswerModel,
                           modes=(ResearchMode.WORKFLOW,))
assert records[0].answer.endswith("unique-tail-after-4000")
assert records[0].evidence[0]["body"] == "checkpoint facts"
```

- [x] Run tests, then implement optional store lookup/claim/save around existing application path. Save application errors as failed, preserve cancellation, collect evidence-read errors separately without losing application output, use outer `asyncio.timeout`.
- [x] Before real CLI calls require output directory and explicit batch ceilings; reject real legacy `--judge` until independent budgeted quality evaluator exists. Validate manifest before constructing model; disable cloud tracing. Offline defaults and v1 tool export stay compatible.
- [x] Seed resumed batch usage from stored counts; incomplete claims cannot silently reset limits. Output complete records, manifest, quality-ready export v2, legacy tool export and engineering report.
- [x] Run focused tests, full offline suite, standalone Ragas tool suite and scripted command→resume probe. Review and record results. Offline HTTP is blocked; the old-CLI RED-stage real-entry incident is disclosed separately, with unknown requests/expense and no benchmark artifact.

## Task 4: Fair simple baseline and governed real assets

**Files:** Create baseline.py, assets.py, tests/eval/test_baseline.py, test_assets.py; extend matrix selection using explicit system name; add data card and versioned datasets/corpora.

**Interfaces:** `build_baseline_research_graph()` produces a fixed retrieval ResearchOutcome through the real ToolGateway; it is registered in an evaluation-only runtime, and the normal ApplicationResearchService/response graphs produce the authoritative result. `run_matrix(..., include_baseline=True)` exposes the baseline under a separate system label. Dataset assets add source metadata/split/reference facts without exposing them to runtime. Asset import reads pinned licensed sources, records exact hash and source locations.

- [x] Tests use two different gold answers with identical user question; baseline input is identical. Compare actual returned answer/source records, never assert only fake call counts.

```python
assert first.answer == second.answer
assert first.mode == "baseline"
assert first.evidence_urls == ["https://example.org/doc"]
```

- [x] Implement fixed search with question text, up to three ordered fetches through actual ToolGateway, writer using same context envelope/citation validation and limits. No manual recall or reasoning loop.
- [x] Build 30 questions with six categories × five, topic/source-group split 12/18; verify each gold fact against allowable primary source text, record reviewer kind. Preserve smoke data. Agent source review only; no human gold. Related concepts overlap across source groups.
- [x] Import five DRB tasks from pinned upstream before viewing output; enforce license and requirements, label local evaluator rather than official RACE/FACT. No references imported; live execution remains unimplemented. Test scoring annotations stay outside runtime projections/inputs.
- [ ] Verify offline matrix, dataset invariants and local source evidence; commit owned generated assets only where redistribution is allowed.

## Task 5: Isolated quality metrics, citation checking and cache

**Files:** Create evaluation/ragas_quality.py, evaluation/tests/test_ragas_quality.py; split focused scoring/cache modules only if complexity warrants.

**Interfaces:** JSON v2 input, per-sample `ok/not_applicable/error`, input hash, framework and evaluator identity. `score_quality(sample, evaluator, budget) -> dict`; input includes final answer, actual evidence, reference facts only on scoring side.

- [x] Controlled correct/incorrect/unsupported answer fixtures must produce discriminative actual Ragas results; external model responses are controlled, Ragas metric implementations real.

```python
assert correct["factual_correctness"]["value"] > wrong["factual_correctness"]["value"]
assert unsupported["faithfulness"]["value"] < supported["faithfulness"]["value"]
```

- [x] Wire pinned-version goal, factual F1 and faithfulness with independent judge config and actual provider attempt limits. Invalid/empty reference or incomplete context is N/A; cancellation is not caught as a score error. Size checks now use each metric's actual inputs; current adapter revalidated offline, not with new paid judging.
- [x] Cache with canonical hashes of all scoring inputs/model/adapter/prompt versions. Modify one reference, evidence or model field and ensure cache miss; failed judgments do not cause Agent reruns.
- [ ] Citation samples store claim, cited URL, source span and support decision; report coverage and extraction failure. Do not mislabel local citation semantics as an upstream metric.
- [ ] Run independent environment tests and bounded external judge calibration only after configured budget; produce blinded human review pack for at least ten paired tasks.

## Task 6: Memory episodes and reliability

**Files:** Create memory_runner.py, tests/eval/test_memory_runner.py, versioned memory scenario data; reuse existing memory/persistence test fixtures.

**Interfaces:** `run_memory_episode(episode, *, enabled, model_factory, limits) -> dict`; stage logs share episode limits and namespace; no production store access.

- [x] Write tests for true cross-thread history absence, expired/updated/deleted record exclusion, unrelated tenant invisibility and crash-safe episode artifact. Long-lived stale-only scenarios remain separate from this TTL slice.

```python
assert episode_result["cross_namespace_hits"] == 0
assert expired_id not in episode_result["recalled_ids"]
assert episode_result["memory_backend"] == "sqlite_lexical"
```

- [x] Run through normal application write/recall/lifecycle with temporary SQLite and controlled clock, memory off skips long-term operations only. Implement six types × two episodes and isolate episode data. Scripted-only; no real memory-quality claim.
- [ ] Add explicit semantic backend option requiring actual embedding/Chroma and identity; mock/lexical results never use semantic label. Fault injections are reported as reliability tests, not natural task quality.
- [ ] Verify lifecycle/state/TTL deterministically and independently judge only applicable generated answers. Record missing config as unmet validation, not fake passing score.

## Task 7: Paired analysis, CI and real evidence delivery

**Files:** Create comparison.py, tests/eval/test_comparison.py; update .github/workflows/ci.yml only evaluation-scoped jobs; add reports/guide/resume artifacts under docs/evaluation and docs/resume.

**Interfaces:** `compare_records(records, scores, *, seed=0) -> dict`; grouping is by dataset split, task ID, system, repeat; threshold config is explicit versioned developer calibration.

- [x] Test repeat aggregation, failure denominators, zero coverage, null interval with one pair, deterministic paired bootstrap, no conflation of public/private/synthetic datasets.

```python
assert report["attempted_tasks"] == 4
assert report["completed_tasks"] == 2
assert report["quality_coverage"] == 0.5
assert report["paired_tasks"] == 1
assert report["paired_interval_95"] is None
```

- [x] Implement per-task aggregate then paired resampling with fixed seed, categorical means and latency quantiles; expose all exclusions and failures. Do not invent weighted total or industry threshold.
- [ ] CI runs deterministic project/isolated scorer checks without keys/network; real experiment commands require explicit manifest and budget. Jobs/Dockerfiles configured and local suites verified; packaged Linux and remote CI execution still unverified (local Docker daemon unavailable).
- [ ] After user confirms budget, run six research + four memory calibration units, save all outputs and actual usage. Confirm full 120 research + 48 memory + 10 public run scale using observed expense before launch.
- [ ] Complete source/human review records, failure report, actual comparative metrics, reproducibility guide and résumé/interview wording. If budget or human review is missing, mark those acceptance items incomplete and request only required missing input.

## Self-review and execution tracking

Spec coverage: dataset governance Task 4; complete records/reproducibility Tasks 1–3; baseline Task 4; metrics/calibration Task 5; memory/reliability Task 6; statistics/CI/real evidence Task 7. No API budget or human review is inferred from code authorization.

This plan is not a completion report. Checkboxes are updated only after executing their test/implementation/review cycle; measured API results are not substituted with scripted contract scores.

## Execution status — 2026-10-02 initial pilot

Tasks 1–3 implemented and reviewed. Baseline from Task 4 and native Ragas metrics/cache from Task 5 implemented. Source-verified pilot has one development question, not the complete 30-question dataset. Citation semantics, public subset, memory episodes, paired statistics, CI and human review remain incomplete.

User selected a smaller calibration than Task 7's original recommendation: one real-source question × baseline/Harness, research ≤160 SDK-facing Provider attempts, scoring ≤24. This replaces the proposed six research/four memory calibration units for this run, not the overall acceptance targets.

Verification: full project suite 629 passed / 2 real tests deselected; independent scorer suite 28 passed; 12 scripted plumbing runs with resume. Formal real calibration consumed 30 research + 16 judging attempts, six native quality results, with baseline partial failure retained. Research and quality resume did not add attempts. 148 manifest-pinned source/data/dependency files were copied and hash-verified into the experiment snapshot.

## Governed assets continuation — 2026-10-02

The prior continuation added response caps, paired analysis and 24 scripted SQLite memory variants; see docs/evaluation/benchmark-continuation-20261002.md. This continuation freezes 30 primary-source tasks (12 dev / 18 test), 14 unmodified MIT-licensed docs, 47 literal spans, source-group separation, agent review and zero human-review claims. CLI benchmark/split preflight and gold-invariance are tested; data bytes survive Windows Git checkout.

Five original DRB tasks [17,19,20,66,68] are imported from a pinned Apache-2.0 upstream. Selection reasons are frozen before outputs; no upstream reference/model-output files read. Public live-web execution, official scoring and complete research matrix remain incomplete. No paid API calls added; old artifacts remain unchanged. Execution/report details: docs/evaluation/governed-assets-20261002.md.

The offline RED-stage old-CLI incident has unknown usage, was stopped, and is excluded from formal data. Current system is the first auditable real-data slice, not complete benchmark acceptance. Details: docs/evaluation/experiment-records.md and docs/evaluation/real-pilot-20261002.md.

## Continuation status — 2026-10-02

Response length is explicit and manifest-bound, verified offline but not recalibrated with a real model. Task 6's 12 temporary-SQLite lifecycle episodes and on/off counterparts completed as 24 scripted variants (7/7 positive on hits, 0/7 off hits; zero isolation or lifecycle violations); semantic retrieval and real answer-quality judging remain incomplete. Task 7's question-level paired analysis implemented and applied offline to the frozen real pilot; all-output n=1 has null intervals, completed-only n=0. Exact judged-input identity is checked. No additional real API requests.

Verification: 670 project tests passed / 2 real deselected; 28 isolated scorer tests passed. Memory source snapshot pins 153 files; durable resume is byte-identical. Full dataset, public subset, citation semantics, real memory calibration, CI and blind human review remain incomplete. Corrected the earlier hypothesis of Store evidence loss: Store was never fetched. See docs/evaluation/benchmark-continuation-20261002.md for results, reproducibility and honest résumé scope.

## CI and long-context diagnosis — 2026-10-02

Offline scorer CI is configured with its own locked image/context and no secret injection; backend and scorer test RUN instructions disable network after tokenizer setup. Local project suite: 714 passed / 2 real excluded; independent scorer: 34 passed. Local Docker daemon is unavailable, so neither packaged Linux build nor remote GitHub run is claimed verified.

Per-metric input-size applicability fixed and adapter identity advanced; old real scores were not overwritten. Three preselected dev questions × two systems yielded six scripted diagnostic records, with 10 literal-span/run checks: 2 not fetched, 8 stored/selected but not fully visible to responder. This is a conservative delivery check, not a quality success rate. Production response excerpt selection remains unchanged pending design approval.

Final diagnostic source snapshot: 177 files; identity 22209e0c38131f2f8a97f12fd767d71a71e3fc1d0cf637586a56b3f3c1cdd61e. No new paid Provider calls. See docs/evaluation/ci-long-context-20261002.md for evidence, CI limits and proposed query-based selection.
