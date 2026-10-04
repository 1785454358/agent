# Minimal Coverage Planning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 初始规划优先最少互补事实查询，减少近义与过程性任务，不裁掉合法问题。

**Architecture:** 只修改现有 planning_instruction 返回文本，三个策略复用同一入口。保持所有解析、封存、补查和执行路径。

**Tech Stack:** Python、LangGraph、pytest-asyncio；真实校准用现有 eval CLI 与隔离 Ragas 0.4.3。

**Spec:** ../specs/2026-10-03-minimal-coverage-planning-design.md；用户选择 A、审阅后回复“开始”，授权实施与登记的同预算复测。

## Global Constraints

- 优先 1–min(3, limit)，不是硬裁成三项；默认上限 P&E 6 / MA 5 / Workflow 3，requirements 1–6 不变。
- 合并近义答案要点，保留显式子问题和必要事实边界；执行过程不是独立研究 assignment，真正事实核查仍合法。
- 生产只改 backend/src/deeptrace/strategies/planning.py 的规划文本；不修改解析/schema、补查、预算/重试/轮数、证据/恢复、模型或评分。
- 提示消费测试按已批准规格检查实际模型输入，不声称离线脚本证明语义去重或节省调用。
- 没有可用 subagent/executing-plans 技能，沿既有内联执行方式，不再询问执行形式；五轴自审。
- 大量先前工作树改动属于既有工作，保持原样，不整体 stage/提交；实现留在工作树，用哈希快照留样。运行完整回归和付费批次时不改源码/HEAD。

---

### Task 1: 共享提示与实际消费回归

**Files:** Modify backend/src/deeptrace/strategies/planning.py；Create backend/tests/strategies/test_minimal_planning_contract.py。

**Interfaces:** 保留 `planning_instruction(query_field, limit) -> str`。真实 `build_plan_node(limit)`、`build_plan_queries_node(limit)`、`build_supervisor_plan_node(limit)` 接收现有 state 和 Runtime(context=fixture.context)，输出既有 plan_tasks/queries/assignments 及 requirements。

- [x] 写模型输入消费测试：三模式 × limit 1/2/6，独立字面期待优先 1-1 / 1-2 / 1-3；验证最少互补、独立事实、不单派过程、合法事实核查及完整原始任务/约束。

```python
raw = await factory(limit)(state, Runtime(context=fixture.context))
assert raw[state_key] == ["Alpha release date"]
assert "优先1-2条" in captured_prompt  # limit=2，外部模型边界而非读取源码
assert "From supplied documentation" in captured_prompt
```

- [x] 写保护测试：limit=4 时四个独立 query/requirement 不裁成三项；非法 JSON / 非法执行约束回退原始查询；旧 metadata 缺省兼容，约束和封存/checkpoint 保持。

```python
assert raw[state_key] == [
    "Alpha release date", "Beta license", "Gamma supported OS", "Delta formats"
]
assert [r.id for r in raw["requirements"]] == ["r1", "r2", "r3", "r4"]
```

- [x] RED：backend 下 `.venv/Scripts/python.exe -X utf8 -m pytest tests/strategies/test_minimal_planning_contract.py -q --tb=short`，契约缺失断言失败而非导入/夹具错误；现有保护行为初跑可绿。
- [x] GREEN：只在 planning_instruction 中补最小覆盖提示；保留现有 JSON example、字段、事实/约束分区说明。不添加宿主裁剪或语义模型。

```python
f"优先1-{min(3, limit)}条覆盖完整问题的最少互补查询，"
"只有更多独立问题确需研究时才增加；上限不是应凑满的数量。"
```

- [x] 新测试与既有规划/补查/三模式/待办/支持/恢复测试通过；在 backend 下对唯一生产文件和新测试运行 Ruff check 与 format --check；对照上批 source_snapshot 确认唯一生产差异，五轴审查。

### Task 2: 冻结验证与真实数据留样

**Files:** Create docs/evaluation/minimal-planning-validation-20261003.md；Modify docs/README.md、本计划/规格流程状态；新增三个登记的 tmp 输出目录。

**Interfaces:** 不改变 eval manifest/source_identity、JSON v2 导出、Ragas quality_scores、compare_cli 或严格续跑身份。

- [x] 冻结源码和 HEAD，backend 下运行完整 `pytest -m 'not real' -q --tb=short`；隔离 `.venv-ragas` 跑 evaluation/tests。运行时不改源/提交。
- [x] 付费前登记三题/三模式/唯一 batch、模型/预算；用 load_questions/load_corpus + _content_hash 核对 DTO 哈希与 analysis-card；目录需不存在，凭据只验证存在，gold 只进评分侧。
- [x] 一次研究批次，在 backend 下运行：

```powershell
.venv/Scripts/python.exe -X utf8 -m deeptrace.eval --model real --modes plan_execute,workflow,multi_agent --repeats 1 --response-mode answer --response-max-chars 2000 --max-model-calls 40 --max-tool-calls 24 --max-provider-attempts 80 --max-batch-model-calls 360 --max-batch-provider-attempts 720 --agent-iterations 12 --max-output-tokens 4096 --run-timeout 360 --dataset ../tmp/evidence-loop-real-20261002-assets/questions.jsonl --corpus ../tmp/evidence-loop-real-20261002-assets/corpus.jsonl --run-prefix minimal-plan-real-answer-20261003 --out ../tmp/minimal-plan-real-answer-20261003
```

- [x] 按 manifest.source_files 逐份 Copy-Item 保存 source_snapshot，先验证源/目标解析路径在项目/批次目录内并校验 SHA-256；不复制 .env；新测试另存并登记 hash。等待批次结束，不重跑、扩预算或调整实现。
- [x] 一次原生评分与严格统计：

```powershell
.venv-ragas/Scripts/python.exe -X utf8 evaluation/ragas_quality.py --input ../tmp/minimal-plan-real-answer-20261003/quality_eval.json --out ../tmp/minimal-plan-real-answer-quality-20261003 --max-provider-attempts 144 --env-file .env
.venv/Scripts/python.exe -X utf8 -m deeptrace.eval.compare_cli --input ../tmp/minimal-plan-real-answer-20261003/quality_eval.json --scores ../tmp/minimal-plan-real-answer-quality-20261003/quality_scores.json --metadata ../tmp/evidence-loop-real-20261002-assets/analysis-card.json --out ../tmp/minimal-plan-real-answer-comparison-20261003
```

- [x] 结束后再次核对 source_identity/快照、judge 与旧批配置一致；逐题记录初始 query/assignment/requirement 数、实际分支与各角色调用、纯待办轮、完成/失败原因、非空答案、计量、评分覆盖和 N/A。
- [x] 旧新同模式对照只作三题 dev 诊断，不作因果/总体/产品比较；没有新 baseline，配对 n=0 / delta / CI=null。保留失败、partial、NA、评分粒度问题和待优化依据，不宣称生产联网 E2E 或一定可靠。

## 自审

唯一生产入口，既有所有边界不变；优先范围尊重较小 limit，不硬裁合法四项问题，保留事实核查与原始任务。TDD 和脚本保护回归不冒充真实收益。真实预算、评分和数据均照规格；既有 dirty 工作保留，不增加部署或依赖操作。
