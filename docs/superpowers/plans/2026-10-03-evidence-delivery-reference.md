# Evidence Delivery and Host References Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Preserve bounded research reads across graph boundaries and resolve visible short references into verbatim supports without changing quality scoring.

**Architecture:** Keep scheduling in the three strategies. Put read-anchor validation/merging in a domain DTO and tool-boundary helper; put reference draft/resolution and evaluation materials in focused shared modules. Existing legacy evaluation types remain decodeable; new research uses contract v3.

**Tech Stack:** Existing Python, Pydantic, LangGraph, pytest; backend .venv and independent .venv-ragas. No dependency addition.

**Spec:** ../specs/2026-10-03-evidence-delivery-reference-design.md

## Global Constraints

- 每分支最多64个唯一 anchors；最多8份来源，每来源3000字符；每调用最多128个引用单位，每单位1至500字符。
- 原始正文、坐标、哈希、租户与可见性校验不放宽；读过不等于事实覆盖。
- 新研究 evidence_contract_version=3；旧完成 v2 可读取，旧中途状态不能派发新研究。
- 真实复测：三题、三模式各一次，Answer最多2000字符，长时记忆关闭。
- 模型 doubao-seed-2.0-lite、temperature=0、max output4096；每运行40逻辑 / 80 Provider / 24工具 / 12轮 / 360秒；整批360逻辑 / 720 Provider。
- 隔离 Ragas0.4.3、原裁判/scorer/输入限额，只评分一次，最多144 Provider；不改gold、不重跑挑分。
- 当前工作树包含大量既有未提交内容，只操作本次文件，不整体提交；每任务记录 RED/GREEN 与审查结果。

## Execution

用户已要求开始实施。本地目录没有 executing-plans / subagent-driven-development 技能；按本计划逐项在当前会话执行，采用已读取的 TDD 和 code-review-and-quality 作为验证/审查流程。不创建新任务或无关 worktree。

### Task 1: Capture and serialize actual read anchors

**Files:** Create backend/src/deeptrace/domain/evidence_anchor.py and backend/src/deeptrace/harness/read_anchors.py; modify domain/research.py, harness/agent_state.py, harness/agent_tools.py, harness/agent_executor.py, harness/checkpoint.py. Create tests/harness/test_read_anchors.py.

**Interfaces:** ReadEvidenceAnchor(evidence_id, version, content_hash, start, end); merge_read_anchors(left, right) -> list[ReadEvidenceAnchor]; capture_read_anchors(preview, evidence_id) -> tuple[list[ReadEvidenceAnchor], list[str]]. ResearchTopicOutcome.read_anchors defaults empty; Agent state holds a bounded list plus read diagnostics.

- [x] RED: exercise execute_batch with real read adapter/store and authorized evidence. Assert result.get('read_anchors') contains the actual range, not model text; a checkpoint-restored branch outcome retains it. Unauthorized and malformed previews produce no anchors.

```python
assert [(a.start, a.end) for a in result.get('read_anchors', [])] == [(7, 19)]
assert result['outcome'].read_anchors[0].evidence_id == record.id
```

- [x] Run `.venv/Scripts/python.exe -X utf8 -m pytest tests/harness/test_read_anchors.py -q --tb=short`; verify failure is absent consumer state, not fixture/import failure.
- [x] GREEN: strict DTO/range validation, host-only preview parser, unique stable merge capped64; update tools observation and finalize, explicit checkpoint type registration. Capture only successful actual previews, log malformed/capacity through bounded diagnostics without failing the successful tool call.

```python
anchors = merge_read_anchors(state.get('read_anchors'), observed_anchors)
updates['read_anchors'] = anchors
```

- [x] Verify concurrency ordering, duplicate replay, capacity, cancellation, tenant grants, old outcomes; run harness reading/invariant/recovery tests and review this deliverable.

### Task 2: Build quote units and visible-reference resolver

**Files:** Create tools/evidence_units.py and strategies/evidence_references.py; create tests/tools/test_evidence_units.py and tests/strategies/test_evidence_references.py. Existing tools/evidence_views.py selectors/legacy supports remain intact.

**Interfaces:** select_read_passages(record, body, supports, anchors, *, question, focus_queries, limit) -> tuple[tuple[EvidencePassage, ...], list[str]]; split_quote_units(passages, supports) -> tuple[EvidencePassage, ...]; ReferenceSupportDraft(ref); ReferenceFindingDraft(id, claim, confidence, supports); normalize_reference_findings(drafts, visible_refs) -> tuple[list[Finding], list[str]].

- [x] RED: construct source slices containing backticks/newlines/nonBMP; invoke new boundaries through getattr/import inside tests so missing behavior is an assertion failure. Select one visible ref and assert literal quote and coordinates; unknown/hidden refs and duplicate IDs cannot become supports.

```python
assert finding.supports[0].quote == '`key`\nnot optional. 🧭'
assert finding.supports[0].end - finding.supports[0].start == 21
```

- [x] Run both new test files and verify RED.
- [x] GREEN: validated existing supports first; read anchors revalidated against current record/body before inclusion; overlap subtraction, sentence/line packing <=500, budget and omitted diagnostics, original selector only with remaining room. Keep accepted support quotes intact; no cross-gap concatenation. Resolver trusts only the final current mapping and derives all evidence metadata.

```python
support = EvidenceSupport(evidence_id=p.evidence_id, version=p.version,
    content_hash=p.content_hash, start=p.start, end=p.end, quote=p.text)
```

- [x] Verify <=3000 source slices, <=500 units, overlap, strict integer boundaries, stale/hash/tenant failures, source/anchor drop diagnostics and semantic missing preserved. Review independently.

### Task 3: Shared evaluation view and v3 strategy integration

**Files:** Create strategies/evaluation_materials.py; modify strategies/evidence_evaluation.py, three strategy models/nodes/state, domain/execution.py, domain/research.py, strategies/model_io.py, harness/checkpoint.py. Create tests/strategies/test_reference_evaluation.py; adapt live-contract fixtures/tests, preserving explicit legacy tests.

**Interfaces:** ReferenceEvaluationView(prompt, passages, references, unread_ids, diagnostics, allocation); assemble_reference_evaluation_view(context, question, requirements, evidence_ids, findings, read_anchors, budget, pinned). New ReferenceExecutorDecision / ReferenceWorkflowEvaluation / ReferenceSupervisorEvaluation retain routing fields; legacy DTO classes remain registered. require_evidence_contract is v3-only for new actions, coverage_complete validates historical v2 and v3 without granting dispatch authority.

- [x] RED: all three real node entry points take v3 state/outcome containing a narrow read missed by the broad selector; scripted evaluator finds text in final view and returns supports=[{'ref': matching['ref']}]. Assert coverage/supports reflect that actual input. v2 mid-run state must raise incompatible_evidence_contract.

```python
result = await node(state, Runtime(context=fixture.context))
assert result['findings'][0].supports[0].quote == FACT
assert result['coverage'].items[0].status == 'covered'
```

- [x] Run targeted reference integration/requirements tests, observe RED, then implement material builder with max8 sources/128 units and whole-block token allocation. Number only actually visible units; emit visibility events after final selection, isolate event failures.

```python
refs = {f'p{i}': p for i, p in enumerate(visible, 1)}
findings, diagnostics = normalize_reference_findings(assessment.findings, view.references)
coverage = normalize_coverage(requirements, assessment.coverage, findings)
```

- [x] Switch production creation/guards/outcomes to v3 and new schema; preserve old assembler/resolver and decode DTO as compatibility surfaces, not reachable live fallback. Update scripted evaluation gateway and test inputs to short-ref contract without altering metric/scoring code or semantic expectations.
- [x] Verify hidden units, tiny token budget/pinned overflow, full JSON token accounting, invalid coverage and mixed findings; test old completed checkpoint roundtrip and v3 new draft roundtrip, three graph routing/recovery tests. Review module boundaries.

### Task 4: Writer and memory/version consumers

**Files:** Modify responses/evidence.py, responses/graph.py, harness/graph.py, harness/memory/lifecycle.py as required to recognize v3 while keeping existing support validation; tests/responses/test_supported_findings.py plus new tests/responses/test_evidence_gap_causes.py and existing memory tests.

**Interfaces:** Existing ResponseMaterials/ResponseInput/ResearchOutcome remain public; expose structured failure causes through existing pinned writer context, no new API DTO. Read diagnostics are retained in research diagnostic gaps/outcome gaps, not counted as missing facts by themselves.

- [x] RED: v3 supported research must use support-first source material; old v2 completed remains supported. For partial invalid_support_reference/evaluation_unavailable capture actual responder prompt and verify causes are separated from factual coverage without any newly marked covered requirement.

```python
assert materials.grounded
assert support.quote in materials.sources[0]
assert result.status == 'partial'
```

- [x] Implement v2/v3 grounded readers and v3 producer recognition without widening old resume dispatch; writer pinned instructions prohibit whole-corpus absence claims from validation/drop failures and require explicit partial limitations. Use existing diagnostics, no extra retry/model.
- [x] Run Answer/Report/materials/memory and harness finalization tests, reviewer gate.

### Task 5: Offline acceptance and registered real experiment

**Files:** Create docs/evaluation/evidence-delivery-validation-20261003.md; update docs/README.md; plan checkboxes/implementation notes. No metric/gold mutation.

- [x] Read code-review-and-quality SKILL.md fully and review correctness, architecture, security, performance, test quality; fix regressions only within approved scope using TDD. Run targeted Ruff check/format.
- [x] Freeze source after fixes, run full backend `.venv/Scripts/python.exe -X utf8 -m pytest -m 'not real' -q --tb=short` and isolated `.venv-ragas/Scripts/python.exe -X utf8 -m pytest evaluation/tests -q --tb=short`; no source edits during checks.
- [x] Check preregistered directories absent; verify normalized dataset/corpus, limits/context/model/judge against previous manifest. Record manifest source hash snapshots and new test hashes before real research. No credential printing.

```powershell
.venv/Scripts/python.exe -X utf8 -m deeptrace.eval --model real --modes plan_execute,workflow,multi_agent --repeats 1 --response-mode answer --response-max-chars 2000 --max-model-calls 40 --max-tool-calls 24 --max-provider-attempts 80 --max-batch-model-calls 360 --max-batch-provider-attempts 720 --agent-iterations 12 --max-output-tokens 4096 --run-timeout 360 --dataset ../tmp/evidence-loop-real-20261002-assets/questions.jsonl --corpus ../tmp/evidence-loop-real-20261002-assets/corpus.jsonl --run-prefix evidence-delivery-real-answer-20261003 --out ../tmp/evidence-delivery-real-answer-20261003
.venv-ragas/Scripts/python.exe -X utf8 evaluation/ragas_quality.py --input ../tmp/evidence-delivery-real-answer-20261003/quality_eval.json --out ../tmp/evidence-delivery-real-answer-quality-20261003 --max-provider-attempts 144 --env-file .env
.venv/Scripts/python.exe -X utf8 -m deeptrace.eval.compare_cli --input ../tmp/evidence-delivery-real-answer-20261003/quality_eval.json --scores ../tmp/evidence-delivery-real-answer-quality-20261003/quality_scores.json --metadata ../tmp/evidence-loop-real-20261002-assets/analysis-card.json --out ../tmp/evidence-delivery-real-answer-comparison-20261003
```

- [x] Run each command only after predecessor artifacts validated; report all9 outcomes, 27 metric slots/coverage, usage and dropped support diagnostics, immutable scoring/snapshot identities. No re-run/cherry-picking. No fresh baseline => strict pairs n=0/delta null. State limitations (known dev questions, same-model judge, frozen local corpus, no independent human review) alongside quality results.

## Self-review

- [x] Spec responsibilities mapped to five independently reviewable deliverables; Task3 connects Tasks1/2.
- [x] Short refs never become persistent proof; v3 dispatch separated from v2 historical reads.
- [x] No new dependency/budget/judge; real test commands use approved caps and unique registered directories.
- [x] No missing signatures or placeholder sections. Implementation requires honest RED, not expected-error collection failures.

## Implementation evidence

- Task1: 三模式实际入口缺少 anchor 的断言 RED，strict header boolean 回归单独 RED 后修复；相关读/恢复回归45 passed。
- Task2: 新模块首次9项失败是接口缺失（在测试函数内导入），不是9项已有逻辑断言失败；实现后配合旧 selector 回归34 passed。没有把导入失败称为语义 RED。
- Task3: 三模式 v3 入口旧版本 guard RED；完整 v2 mid-run 夹具确实 DID NOT RAISE 后再修。补充材料可见性、128 units 和 token 账本测试为实现后验证，包含一项测试夹具修正，不虚报 TDD。
- Task4: v2历史兼容已通过；v3消费者2项 RED后修复；脚本协议迁移保留语义/恢复门禁断言，定向208 passed。
- 五轴自审：职责独立且三模式共享；原文/版本/哈希/租户检查保留；选择数量有界且不增加 Provider；兼容读取与新派发分开；真实质量由未修改的隔离评分器验证。44个本次Python文件 Ruff check / format --check 通过。
- 真实调用前冻结：最终全量1043 passed/2 deselected（116.54秒），隔离评分器34 passed（6.67秒）；190份manifest源留样和6个新增测试留样/哈希已核验，研究批次已启动。运行中不改源或HEAD。
- 真实研究/评分/严格compare已完成，各执行一次：7 completed/2 partial、25有效指标/2输入限额N/A。F1主指标P&E0.493333；WF0.613333、MA0.530000。所有输出保留，不夸大FA的available-case满分；具体根因、裁判限制、冻结复核与原始留样见验证报告。
