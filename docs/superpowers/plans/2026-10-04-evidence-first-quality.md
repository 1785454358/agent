# Evidence-first Quality Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 恢复真实联网回答质量，替换重复结论加工与不完整原文输入，再验证质量不降时是否减少搜索、耗时和token。

**Architecture:** 三模式共用现有Gateway、证据仓库、阅读视图和全局评估。以实际页面URL区分来源，阅读原文与短引用分开，评估直接抽取事实。保留权限、checkpoint、Writer与调度，不添加Agent或依赖。

**Tech Stack:** Python 3.12, Pydantic, LangGraph, pytest, Ruff, Tavily, independent Ragas environment.

**Spec:** `docs/superpowers/specs/2026-10-03-evidence-first-quality-design.md`，用户2026-10-04确认。

## Global Constraints

- EvidenceSupport最多500字符、Finding最多3条supports；引用只绑定实际可见原文。
- 8k软目标、最近3组近期对话、现有硬预算、持久历史/原文/checkpoint均保留。
- 每分支12轮、每运行40 logical/80 Provider/24 Gateway/360秒；生产默认8及显式.env优先规则不改。
- 首轮三模式各一次：研究批次120 logical/240 Provider、评分48 Provider。
- doubao-seed-2.0-lite、temperature=0、输出4096、Answer2000字符、关闭记忆；不改模型、评分器、金答案或.env。
- 无新增Agent、服务、依赖、LLM摘要；旧候选记录兼容，但不作为accepted事实。
- 保留全部failed/partial，不择优重跑或重评分。多题批次必须先另行预登记。
- 当前没有可用subagent-driven-development/executing-plans技能，采用本会话inline TDD，不宣称使用了不存在的技能。
- 仓库已有大量dirty更改；先留样当前src/tests，源码提交只包含本轮明确的增量，不整体提交已有改动。

## Task 1: 实际URL来源身份

**Files:** Modify `backend/src/deeptrace/tools/adapters.py`; Create `backend/tests/tools/test_source_identity.py`.

**Interfaces:** 保持`_ResearchToolAdapters.fetch_page(arguments, context) -> ToolAdapterResult`与EvidenceDraft；`canonical_url`承载实际来源键，metadata保留publisher canonical。

- [x] 用真实适配器/内存仓库写失败测试：两份RawDocument分别为3.11英文/3.14中文，共用publisher canonical；摄取后两者均ACTIVE、ID不同、引用URL保留版本与语言。另测真实重定向、无final URL回退及同actual URL更新。

```python
assert first.canonical_url == "https://docs.example.org/3.11/task"
assert second.canonical_url == "https://docs.example.org/zh/3.14/task"
assert (await store.get("tenant", first.id)).status.value == "active"
```

- [x] `backend/.venv/Scripts/python.exe -m pytest tests/tools/test_source_identity.py -q`（工作目录backend），观察canonical误合并的断言失败。
- [x] 最小替换来源选择，metadata添加发布者canonical，不改仓库版本策略。

```python
source_url = document.final_url or document.requested_url
# existing metadata additionally stores publisher_canonical_url
```

- [x] 运行新测试、`tests/tools/test_adapters.py`、`tests/tools/test_gateway.py`、证据仓库测试；核对幂等及supersede仍有效。
- [x] 自审来源授权/SSRF未变；新增测试及本轮增量通过前后源码留样可重建，不打包既有dirty更改提交。

## Task 2: 完整阅读单元与短引用分开

**Files:** Modify `tools/evidence_views.py`, `tools/evidence_read.py`, `harness/research_findings.py`, `strategies/evaluation_materials.py`; Create `tests/tools/test_coherent_read_context.py`, `tests/strategies/test_evidence_first_materials.py`.

**Interfaces:** 保持EvidencePassage、ReadEvidenceArguments、ReferenceEvaluationView；原文passages整组显示，短引用仍最多500字符；`number_read_preview(preview, references)`保留兼容旧编号登记。

- [x] 写真实预览测试：单passage内条件跨500字符且正文有内联多行，编号后所有原文仍显示、坐标匹配、不因重复metadata删除条件；紧预算整组省略并标定位。

```python
assert "Other awaitables will not be cancelled." in numbered_preview
assert all(body[p.start:p.end] == p.text for p in view.passages)
```

- [x] 定向pytest观察旧编号删除尾部/按短单元丢上下文的失败。
- [x] 修改句群边界：空行/完整句末，而非任意单换行；保持raw坐标与明确省略。编号预览减少重复元数据，原文展示不被500字符引用限制裁断。评估同一阅读组的短p引用整组分配预算，不保留孤立前半条件。

```python
# paragraph/sentence ranges address the unchanged original body
# select whole reading groups; generate <=500-character citation refs inside them
```

- [x] 评估输入移除research candidate claim/confidence及candidate supports优先级；保留实际来源元数据、固定需求、合法accepted支持和相关原文。
- [x] 运行阅读、引用、材料/预算、外租户和9th-source回归；只更新被规格明确取代的旧候选展示断言，不能弱化权限及原文断言。
- [x] 自审短引用不能单独充当事实证明，工具与评估schema兼容；留本轮增量diff。

## Task 3: 不重复加工候选，已读原文驱动收尾与上下文

**Files:** Modify `harness/research_completion.py`, `harness/agent_tools.py`, `harness/prompts.py`, `harness/policies/agent_context.py`, `strategies/evidence_evaluation.py`; Create `tests/harness/test_read_first_completion.py`, `tests/harness/test_retained_read_context.py`.

**Interfaces:** `validate_completion(*, task, findings, todos, context, read_anchors)`检查实际已读授权来源；原有数据和函数调用兼容。state中read_anchors持久留档，模型只看去重相关已读原文与近期完整交换。

- [x] 写三模式read→finish、不record的失败测试；未读/失效/未来引用/未完成todo/前置错误仍partial，checkpoint和工具配对完整。

```python
assert result["outcome"].agent_outcome.stop_reason == "completed"
assert result["outcome"].research_findings == []
assert result["outcome"].read_anchors
```

- [x] 观察现实现finish_no_valid_findings失败，再将完成前提改为有效read anchor；候选不能代替actual read。仅修改已确认的收尾前提，保留批次/取消/失败优先规则。
- [x] 写旧阅读退出最近3组后仍保留关键原文、去重不重复发送、软预算不丢条件/硬预算仍失败的测试，观察失败。
- [x] 上下文从实际成功read工具结果提取有界去重原文，不生成模型摘要，不输入候选claim；原文与来源身份保持，state不修改。更新research/evaluator提示，使record成为可选、评估直接依据原文，不将summary视作证据。
- [x] 运行三模式共享循环、checkpoint、响应/引用、旧候选兼容测试；记录新增schema输入大小与实际模型视图估算。
- [x] 自审并留增量diff；不删除仍有兼容消费者的旧工具/记录实现。

## Task 4: 预算失败分类与已有联网入口扩展

**Files:** Modify `harness/agent_tools.py`, `eval/__main__.py`, `eval/experiment.py`, `eval/report.py`; Test `tests/eval/test_live_boundary.py`, `tests/harness/test_agent_invariants.py`.

**Interfaces:** 复用现有runner参数；live_web接受显式dataset/modes/repeats，仍拒绝scripted/frozen环境和未配置真实凭据。预算拒绝映射`budget_exhausted`，不是供应商故障；cache/SDK请求计量边界不改变。

- [x] 写Gateway额度在dispatch前拒绝仍partial/budget_exhausted的失败测试；写多题/模式子集/repeats参数成功解析但未启动API的测试。
- [x] 运行并确认失败，再替换现有固定诊断参数限制及RequestLimitReached分类；报告标题从manifest live_web派生。

```python
# permit explicit positive repeats / validated mode subset for live_web
# preserve resource caps and require a real model and live retrieval factory
```

- [x] 验证CLI、manifest、预算、输出目录隔离、报告live/frozen标签及原schema；不改Ragas文件和依赖。
- [x] 自审绝无隐藏API请求/无限重试或预算提高，留本轮增量diff。

## Task 5: 回归、自审与同口径真实验证

**Files:** Create `docs/evaluation/evidence-first-validation-20261004.md`; reuse eval CLI, independent `evaluation/ragas_quality.py`, frozen-artifact audit helpers.

- [x] `backend/.venv/Scripts/python.exe -m pytest tests -m 'not real' -q --tb=short`（backend cwd）、`.venv-ragas/Scripts/python.exe -m pytest evaluation/tests -q`、Ruff变化模块、compileall。修复失败须回到TDD，不改评分器。
- [x] 五轴自审：来源版本/真实引用/条件完整性、兼容边界、简化是否减少重复加工、权限/SSRF未变、原文选择/序列化有界。检查新增/不可达代码，不擅自删除旧兼容实现。
- [x] 登记`evidence-first-answer-20261004`源码哈希/配置/原题/评分器；来源与src/tests留样不复制.env，确认与旧模型/预算一致。
- [x] 三模式真实研究各一次，保留退出码、failed/partial和全部产物；独立Ragas评分一次，上限48 Provider。未达恢复门槛不得进入扩大实验或择优重跑。
- [x] 报告质量、严格版本/内容验收、全部开销/搜索与重试及有效分母；输入输出token、评分用量分开，无匹配合格成功样本成本NA。
- [ ] 恢复合格后封存3道新增题加诊断题、主模式每题每臂2次/辅模式诊断各臂一次，登记旧/新源码、顺序与批次硬上限，再分批联网配对；未登记不启动。质量三项/成功率不降低、配对成功平均时间/token/搜索都不增加且至少一项降低才报效率成功。
- [x] 更新复选框、架构文档与全部真实结果；未达到恢复门槛，扩大配对未启动。源码与文档保留工作区，不整体提交既有dirty修改，不以回归通过冒充目标完成。

## Execution outcome (2026-10-04)

TDD各项先红后绿；完整回归1162 passed/2 deselected，评分环境34 passed；Ruff与compileall通过。已完成预登记三模式真实研究及一次独立评分，全部退出码/partial/评分超时留档。

主模式F1 0.60（未恢复到0.80）且partial；WF 0.83/MA 0.91但来源版本不符，MA Faithfulness超时N/A。原文审计无Writer支持遗漏，源文件及judge身份相同。扩大多题配对按门槛不启动，不择优重跑。详细结果见 docs/evaluation/evidence-first-validation-20261004.md。
