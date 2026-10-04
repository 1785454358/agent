# Planning and Gap Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 分开事实要求与执行约束，修复合法混合补查目标整条误丢弃。

**Architecture:** 新增小型 planning.py 维护初始规划的共享指令及有界解析；沿用 seal_initial_plan 和持久化 v2。补查按主机封存全集验证，再取当前缺口交集。

**Tech Stack:** Python、Pydantic、LangGraph、pytest-asyncio；真实评测使用现有 CLI 和隔离 Ragas 0.4.3。

**Spec:** ../specs/2026-10-02-planning-gap-contract-design.md，用户以“开始”确认实施与三模式复测。

## Global Constraints

- requirements 1–6 项，execution_constraints 可选 0–6 项非空字符串、每项最多 500 字符。
- 不更改原始任务、现有用户约束、支持/引用门禁、持久化 v2、模型/评分标准或预算。
- execution_constraints 不进入持久化状态、不授予权限；旧已封存要求不重写。
- 补查最多 2 条；未知/重复目标拒绝，混合合法目标仅保留 missing/conflicting，纯 covered 拒绝。
- 无可用子代理执行工具及 executing-plans 技能，本会话内联执行并复核；不额外询问执行方式。
- 工作区包含先前改动，不 blanket stage；重叠文件仅按本轮内容编辑，提交纯新增文件和文档，不混入重叠文件的历史修改。

---

### Task 1: 初始规划分区契约

**Files:** Create backend/src/deeptrace/strategies/planning.py、backend/tests/strategies/test_planning_contract.py；Modify 三模式 nodes.py、evidence_evaluation.py（初始解析及 evaluator 指令）。

**Interfaces:** `planning_instruction(query_field: Literal['queries','assignments'], limit: int) -> str`；`parse_initial_requirements(payload: dict | None) -> list[ResearchRequirement] | None`。返回 None 仍由已有全任务降级处理，不从执行约束生成事实要求。

- [x] 写失败用例：可选 execution_constraints 非列表/None/空白/数字/7 项/501 字符时 seal_initial_plan 必须 degraded；旧代码忽略字段，预期失败。验证合法分区不会进入 coverage、原始 task/会话约束保留、Python 版本限制仍是事实要求。

```python
queries, contract = seal_initial_plan('full original task', {
    'requirements': [{'id': 'r1', 'description': 'Python 3.10 restrictions'}],
    'execution_constraints': [' '],
}, ['version query'])
assert contract['decomposition_degraded']
assert queries == ['full original task']
```

- [x] RED：与补查新用例联合初跑 20 failed / 6 passed；非法约束被忽略而非 degraded，有真实三模式节点断言失败，未用导入错误代替复现。
- [x] GREEN：planning.py 中 Pydantic 有界 InitialRequirements 只验证两个分区（metadata 不持久化）；`seal_initial_plan` 使用 parse_initial_requirements；三模式调用共享 planning_instruction 生成同一规则/JSON 形状，保留模式查询字段、上限、背景与完整问题。

```python
class InitialRequirements(BaseModel):
    requirements: list[ResearchRequirement] = Field(min_length=1, max_length=6)
    execution_constraints: list[Annotated[str, StringConstraints(
        strip_whitespace=True, min_length=1, max_length=500,
    )]] = Field(default_factory=list, max_length=6)
```

- [x] 验证：规划/补查及相关回归联合 108 passed；旧输出缺 metadata 仍可用，metadata 与权限无关、checkpoint 不变。

### Task 2: 补查目标全集与缺口交集

**Files:** Modify backend/src/deeptrace/strategies/evidence_evaluation.py（parse_gap_tasks、supplement_plan）；Modify backend/tests/strategies/test_evidence_progress.py（现有 parser 调用）；Create backend/tests/strategies/test_gap_target_contract.py。

**Interfaces:** `parse_gap_tasks(payload, *, gap_ids, requirement_ids, dispatched, limit)`；生产及测试调用必须显式传主机封存全集，无隐式兼容默认值，不能推测 r1…r6 均已封存。既有内部 parser 测试补充全集参数，预期不变。

- [x] 写失败用例：给定封存 {r1,r2,r3}、缺口 {r1,r2}，模型 [r3,r2,r1] 保留 [r2,r1]；未知+合法整体拒绝；重复目标、纯 covered、重复 query 拒绝；坏任务不抢占去重集合。真实 P&E / MA 补查节点验证只派发合法目标，不覆盖 requirements。
- [x] RED：联合初跑中 8 个显式全集参数用例失败、2 个真实补查节点因混合目标丢弃失败；具体行为仍由真实节点测试验证。
- [x] GREEN：传入全集前先验证 gap_ids 是子集；拒绝未知/重复 ID 后，`remaining=[target for target in targets if target in gap_ids]`，空列表拒绝。仅 accepted 任务占 seen，替换目标列表不修改输入 payload，生产传 `{r.id for r in requirements}`。
- [x] 验证：相关 108 项及完整 953 项通过，涵盖三模式集成/恢复/引用门禁。保留 Workflow 初始流程，不新增补查循环。

### Task 3: 验收、快照与真实 API 复测

**Files:** 本计划/规格状态、docs/evaluation/planning-gap-validation-20261002.md、docs/README.md；新实验目录 tmp/planning-gap-real-answer-20261002/ 与 tmp/planning-gap-real-answer-quality-20261002/。

- [x] 全离线：953 passed / 2 deselected；隔离 Ragas 34 passed；改动文件 Ruff check 和 format --check 通过。五轴自审无本轮必修阻断项，未修无关旧 lint。保留并说明一次并发修改导致的严格续跑身份拒绝，冻结后重新全部通过。
- [x] 执行前登记新批次与唯一 ID，规范化 dataset/corpus 哈希与旧 analysis-card 一致，新目录未存在；不新跑 baseline。研究启动后冻结源码与 HEAD，185 份 source_snapshot 逐份核对 manifest。

```powershell
.venv/Scripts/python.exe -X utf8 -m deeptrace.eval --model real --modes plan_execute,workflow,multi_agent --repeats 1 --response-mode answer --response-max-chars 2000 --max-model-calls 40 --max-tool-calls 24 --max-provider-attempts 80 --max-batch-model-calls 360 --max-batch-provider-attempts 720 --agent-iterations 12 --max-output-tokens 4096 --run-timeout 360 --dataset ../tmp/evidence-loop-real-20261002-assets/questions.jsonl --corpus ../tmp/evidence-loop-real-20261002-assets/corpus.jsonl --run-prefix planning-gap-real-answer-20261002 --out ../tmp/planning-gap-real-answer-20261002
.venv-ragas/Scripts/python.exe -X utf8 evaluation/ragas_quality.py --input ../tmp/planning-gap-real-answer-20261002/quality_eval.json --out ../tmp/planning-gap-real-answer-quality-20261002 --max-provider-attempts 144 --env-file .env
```

- [x] 两项执行已结束：研究退出码 1（0 completed / 6 partial / 3 failed），281 次 Provider；评分退出码 0，46 次 Provider，17 ok / 10 N/A / 0 error。compare_cli 严格身份校验通过，覆盖/排除统计已导出；无 baseline，配对 n=0，不解释 delta。报告已列逐题状态、语义分数、调用/纯待办次数、完整 usage 和小 dev 局限。
- [x] 报告真实结果：主模式 P&E completed=0/3，F1=0.31（1/3），Faithfulness=N/A（0/3），Goal=1（1/3），不宣称完成率提升或生产可靠 E2E；未自动扩预算、换模型、重评或实施下一轮模块。

## 自审

三个任务覆盖有界分区、模式复用、兼容、未知 ID 安全校验、混合目标/真实补查及离线/真实留样。无持久化字段或新增网络服务，流程与证据格式不扩展。署名方案的语义拆解能力只能由真实轨迹检验，不以提示词字符串测试代替质量评测。
