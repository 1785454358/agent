# Final Evidence Handoff Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 在原预算和评分下修复证据交接与来源约束，真实验收后停止修改，并交付面试资料。

**Architecture:** 已读范围和全文共用结构选段；同一个 evaluator 返回逐来源适用性，宿主过滤 findings 后重算 coverage。适用性随 ResearchOutcome 交给 Writer，拦截旧资料回退。

**Tech Stack:** Python、Pydantic、LangGraph、pytest；独立 `.venv-ragas`，不增加依赖。

**Spec:** `docs/superpowers/specs/2026-10-04-final-evidence-handoff-design.md`（2026-10-04 用户书面批准）。

## Global Constraints

- 不加 Agent、向量服务、模型调用、研究轮数、检索预算或依赖。
- 不改评分口径或重评分挑好结果；新前缀，三模式各一次。
- 只在有效实际已读范围中选择；保持 hash/version/坐标和授权校验。
- 单来源评估 3000 原文字符、全局 token 和引用单位上限不扩大。
- completed 不绕过未完成待办或强退出；来源失败不当完成。
- 工作区已有变化不纳入整文件提交；本会话内逐项执行（执行子技能不可用）。

## Task 1: Shared bounded selection

**Files:** Modify `backend/src/deeptrace/tools/evidence_views.py`, `evidence_units.py`; tests `backend/tests/tools/test_final_read_selection.py`.

**Interfaces:** `select_source_excerpt(body, question, limit, *, focus_queries=None, eligible_ranges=None)`；`select_read_passages` 既有签名不变。

- [x] 写失败测试：两个早期大窗口占满预算，晚读 `BatchAwait` 的完整条件仍应被选中；断言 `"include_errors=True" in text`，所有坐标属于实际读区间。
- [x] `.venv/Scripts/python.exe -m pytest tests/tools/test_final_read_selection.py -q`：先确认晚读条件断言失败。
- [x] `eligible_ranges` 校验后合并；每个区间内 `_source_blocks` 原位取块；间隙重置节上下文。片段选择调用既有实体/节/长度归一算法，不拼接假正文。预算可容纳时保留全部已读正文。`select_read_passages` 删除旧 relevance 排序，保护已有支持后调用共享选择器。

```python
excerpt = select_source_excerpt(body, question, remaining,
    focus_queries=focus_queries, eligible_ranges=available_read_ranges)
for span in excerpt.ranges:
    selected = _merge([*selected, (span.start, span.end)])
```

- [x] 同套件加未读间隙、无命中但短读范围、失效 anchor、已接受支持保护案例，定向回归 `tests/tools` 与 `tests/strategies/test_evidence_first_materials.py`。

## Task 2: Source suitability and evaluator integration

**Files:** Modify `strategies/evidence_references.py`, `evaluation_materials.py`, `evidence_evaluation.py`, three strategy `models.py`/`state.py`/`nodes.py`, `domain/execution.py`; create `tests/strategies/test_source_suitability.py`.

**Interfaces:** `ReferenceSourceCheck(source, status, reason)`；`normalize_source_checks(checks, source_ids, visible_refs) -> (dict, diagnostics)`；`ResearchOutcome.source_eligibility` 为持久化 evidence ID 到状态的可选映射。

- [x] 三模式失败测试：模型给 `s1=ineligible` 却声明 coverage covered，结果必须 findings 空、coverage missing；缺失/重复/未知/uncertain 与混合 supports 都拒绝。
- [x] 执行该文件，确认现有程序错误接受来源，非夹具故障。
- [x] 在既有 Reference DTO 增加 bounded source_checks 默认空列表（历史可解码，但实时缺失不通过）；view 保存本次短来源表；normalize 对 unknown/duplicates/missing/no visible text fail closed。

```python
eligibility, issues = normalize_source_checks(assessment.source_checks,
    view.source_ids, view.references)
findings = [f for f in findings if all(
    eligibility.get(s.evidence_id) == "eligible" for s in f.supports)]
coverage = normalize_coverage(requirements, assessment.coverage, findings)
```

- [x] 原始问题 pinned 作为用户限制；同一调用输出来源与事实判断，不用 URL 证明技术事实。过滤后重算充分性；eligibility 随三种 graph state / final ResearchOutcome 持久化。补查复用已有路由。
- [x] 全局组预算保持原子性；保留已接受支持优先，剩余来源按选段顺序交错而不是最早来源吞完；定向测试实际序列化 token 预算后仍可见多需求关键组。
- [x] 仅更新测试的外部 evaluator 协议夹具，增加与其实际可见来源对应的 source_checks；不生产补字段，不删除完成/缺证据断言。

## Task 3: Writer admission

**Files:** Modify `responses/graph.py`, `responses/evidence.py`; create `tests/responses/test_source_suitability.py`.

**Interfaces:** 消费 `ResearchOutcome.source_eligibility`；历史 None 可解码，当前 evaluator 缺失产生 uncertain 映射而非 None。

- [x] 失败测试：active ids 包含官方指定版与拒绝新版，Writer prompt 和最终合法引用不得出现拒绝来源；直接调用材料装配也不得绕过。
- [x] 执行测试，确认拒绝 URL 仍出现在当前 prompt 的实际失败。
- [x] 两入口均按 `eligibility[id] == "eligible"` 筛选；candidates 不容许混合未批准 supports。加载后传出的 `loaded_evidence` 与引用编号必须一致，不只遮正文。

```python
if research and research.source_eligibility is not None:
    loaded = [r for r in loaded
              if research.source_eligibility.get(r.id) == "eligible"]
```

- [x] 回归 Answer/Report、旧记录解码、恢复和跨工作区权限。

## Task 4: Complete verification and frozen live run

**Files:** Create `tmp/final-handoff-preflight.py`, final registration/source snapshot and experiment output；create `docs/evaluation/final-handoff-validation-20261004.md`.

- [x] `.venv/Scripts/python.exe -m pytest -q -m "not real"`；独立 `.venv-ragas` 运行既有评分测试；ruff/compileall/diff whitespace，自审正确性/复杂度/安全/性能。
- [x] 登记 `final-handoff-answer-20261004`，与上轮配置逐字段比较，封存源码/测试；评分器 hash 必须相同。
- [x] 按既有 live CLI 运行三模式一次，limits 40 logical/80 Provider/24 Gateway/360s 每运行，批次120 logical/240 Provider，12轮每分支，Answer2000字符。
- [x] 独立 Ragas 一次评分，上限48 Provider；报告原始分数、全部错误和 usage；不覆盖或重评分旧结果。
- [x] 审计指定来源、关键行为、当前可见引用、运行前后源码 hash；主模式 completed/F1≥0.80/来源合格后冻结。未通过如实记录，不扩大范围。

## Task 5: Interview delivery

**Files:** Create `docs/resume/深度研究Agent可靠性优化面试背诵版.md`, `深度研究Agent最终实测与面试事实边界.md`; update `docs/resume/README.md`.

- [x] 背诵版含30秒/2分钟介绍，成熟项目差异、标准循环、来源适用性、原子证据交接、预算、补查、记忆、恢复、评测及压力追问；统一说明是设计回答模板，不是虚构经历。
- [x] 事实文件使用本轮实际输出和产物路径，列单题/非heldout/同模型judge边界；可用简历句无虚构百分比或生产成绩。
- [x] 引用已核查的一手代码/文档；不复制过量内容。核对链接存在与统计一致，展示交付文件。

## Plan self-review

规格每一节分别对应 Task 1–5；新签名和字段在其消费者之前定义。失败测试先行，来源检查、coverage、Writer 同一准入边界；无待填占位。用户已要求执行，采用本会话内执行，无另建线程或新依赖。

## Execution record — 2026-10-04

Tasks 1–5 completed in this session. Test-first failures and fixture/protocol updates are detailed in the validation record; the global-budget case first passed at500 tokens, then reproduced the intended failure at420 before implementation. The unavailable execution sub-skills were not invoked; work remained in this chat. Whole-repository Ruff still reports pre-existing/out-of-scope issues; only changed-file lint is reported as passing.

Final offline:1213 passed/2 deselected; independent evaluation:34 passed. Three live modes each ran once, followed by one unchanged-scorer pass. Main completed/F1=1.00/official3.11 source met the approved freeze gate; Workflow source failure and all Goal zeros remain reported. Source/test snapshot hashes verified after scoring. No further implementation changes. Two interview documents and final statistics delivered; no new service, dependency, budget or scoring criterion.
