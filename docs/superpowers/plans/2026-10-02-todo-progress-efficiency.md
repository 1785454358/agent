# Progress-Based Todo Updates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 删除每轮强制待办更新指令，以真实进度驱动更新，保留所有完成和证据门禁。

**Architecture:** 只修改已有共享研究指令和工具说明。复用已有批处理、状态及恢复，不添加执行策略或新状态。

**Tech Stack:** Python、LangGraph、pytest-asyncio；真实校准使用现有 CLI 和隔离 Ragas 0.4.3。

**Spec:** ../specs/2026-10-02-todo-progress-efficiency-design.md；用户已回复“确认”，批准实施与同预算三模式复测。

## Global Constraints

- 保留首次初始化 2–5 个具体待办；schema 仍为 1–20 项。
- 仅初始化/已观察到的进度或计划变化时更新，不强制每轮更新；不能预标未返回工具完成。
- 不改 execute_batch、ExecutionPolicy、预算/重试/分支轮数、初始规划数量、工具授权或 checkpoint schema。
- 测试调用真实 graph/gateway/store；只有外部模型/search/fetch 使用现有测试依赖。提示接收测试只是批准的指令契约验收，不声称证明模型行为或质量提升。
- 无可用 subagent/executing-plans 技能，按既有工作方式内联执行并自审，不重复询问执行方式。
- 工作树含用户已有修改，不 blanket stage，不提交重叠文件的历史修改；留在当前工作树，通过实验快照复现。
- 真实批次只跑一次，3 道已用 dev × 3 模式；不新增 baseline，不运行 test split，不改 gold/评分/模型。

---

### Task 1: 共享指令与真实节点回归

**Files:** Create backend/tests/harness/test_todo_progress_contract.py；Modify backend/src/deeptrace/harness/prompts.py、backend/src/deeptrace/harness/agent_tools.py（仅 write_todos 描述）。

**Interfaces:** 不新增生产函数；已有 `build_research_agent_graph(...).ainvoke({'topic_input': ResearchTopicInput}, context=HarnessContext)` 接收现有 RESEARCH_TOOLS。外部模型收到系统指令与工具 description，工具 schema/角色/状态不变。

- [x] 写指令消费失败测试：三模式真实共享节点把更新策略传给模型，分开检查系统指令与实际绑定工具说明；旧指令缺少进度/禁止预标说明，预期断言失败，而不是导入错误。完整原始任务及用户约束仍传入。

```python
raw = await build_research_agent_graph(max_iterations=1).ainvoke(
    {'topic_input': topic}, context=fixture.context,
)
assert raw['outcome'].agent_outcome.stop_reason == 'iteration_limit'
# 在外部模型边界捕获并核对进度契约，不以脚本模拟推算真实节省。
```

- [x] 写真实批处理/恢复保护用例：初始化 todos + search；观察结果后更新 + fetch；从真实 fetch 返回的 evidence_id 读取原文；成功读取后关闭待办；模型结束。真实 gateway 授权/存储，检查 ToolMessage 一一配对、证据正文及 view 定位、checkpoint 恢复不重复 search/fetch、outcome completed。此能力已存在，可能初跑即绿，明确标为保护回归。
- [x] 写保护场景：未完成待办但有来源 / 已完成待办无来源 / 同批致命错误或预算/取消退出。保留错误与工具配对，不让待办声明抹除强退出；不新增宿主 todo 成功因果校验。
- [x] RED：backend 下 `.venv/Scripts/python.exe -X utf8 -m pytest tests/harness/test_todo_progress_contract.py -q --tb=short`，记录指令消费用例失败与保护用例初跑状态。
- [x] GREEN：系统第一条保留初始化，改为“仅在已观察到的进度或计划变化时更新；计划未变化不重复提交；可与下一步研究工具同批；不能把同批尚未返回的工具请求提前标为 completed”。工具说明包含同一规则、全列表提交和原有结束约束。不修改其他流程。
- [x] 验证新测试、test_agent_invariants、test_evidence_loop_modes、test_recovery 和支持/强退出回归；定向 Ruff check/format 在 backend 下执行。五轴自审明确提示行为仍需真实验证，无新增 runtime→eval 依赖或秘密导出。

### Task 2: 完整验证与真实留样

**Files:** 本计划/规格状态；Create docs/evaluation/todo-progress-validation-20261002.md；Modify docs/README.md；新目录 tmp/todo-progress-real-answer-20261002/、同名前缀质量/统计目录。

**Interfaces:** 现有 eval v2 导出、source_identity、ExperimentStore、Ragas quality_scores 及 compare_cli 保持不变。

- [x] 冻结源码和 HEAD，运行完整 `pytest -m 'not real' -q --tb=short` 与隔离 `evaluation/tests`；全套运行期间不调整实现或提交，避免续跑身份变动。
- [x] 付费前登记模型/边界/唯一 run IDs；验证规范化 dataset/corpus 哈希与原 analysis-card 相同、输出目录未存在、API 凭据仅验证存在。Gold 不进入研究模型。

```powershell
.venv/Scripts/python.exe -X utf8 -m deeptrace.eval --model real --modes plan_execute,workflow,multi_agent --repeats 1 --response-mode answer --response-max-chars 2000 --max-model-calls 40 --max-tool-calls 24 --max-provider-attempts 80 --max-batch-model-calls 360 --max-batch-provider-attempts 720 --agent-iterations 12 --max-output-tokens 4096 --run-timeout 360 --dataset ../tmp/evidence-loop-real-20261002-assets/questions.jsonl --corpus ../tmp/evidence-loop-real-20261002-assets/corpus.jsonl --run-prefix todo-progress-real-answer-20261002 --out ../tmp/todo-progress-real-answer-20261002
.venv-ragas/Scripts/python.exe -X utf8 evaluation/ragas_quality.py --input ../tmp/todo-progress-real-answer-20261002/quality_eval.json --out ../tmp/todo-progress-real-answer-quality-20261002 --max-provider-attempts 144 --env-file .env
.venv/Scripts/python.exe -X utf8 -m deeptrace.eval.compare_cli --input ../tmp/todo-progress-real-answer-20261002/quality_eval.json --scores ../tmp/todo-progress-real-answer-quality-20261002/quality_scores.json --metadata ../tmp/evidence-loop-real-20261002-assets/analysis-card.json --out ../tmp/todo-progress-real-answer-comparison-20261002
```

- [x] 启动后按 manifest 的 source_files 复制 source_snapshot，检查每个解析路径在实验目录/项目内，逐份核对 SHA-256，不复制 .env。等待研究/评分结束，不重跑、扩预算或改源。
- [x] 报告逐题状态、非空答案数（与 answered 不混用）、纯待办轮/逻辑调用、研究分支数、Provider/工具/Token/缺失 usage、Ragas 有效覆盖与 N/A。没有 baseline，delta/CI 不解释。
- [x] 与前批同模式开发诊断分开对照，不能以不同可评分覆盖均值声称因果提升；本批仍非生产实时联网 E2E。若未通过，保留失败和下一步依据，不扩大本轮范围。

**执行结果：** [实现与校准报告](../../evaluation/todo-progress-validation-20261002.md)。966 项后端 / 34 项隔离评分离线回归通过；真实 9 条为 3 completed / 3 partial / 3 failed，非空答案 6；单批研究 247 / 裁判 46 Provider 尝试。纯待办轮 111→67，但 MA 覆盖退步、整体事实质量未证明改善，不标成系统全面可靠。所有结果和 N/A 留档，未扩预算/重跑/重评。

## 自审

两个提示入口同规则；初始化/未完成计划/证据支持/恢复/强退出均有真实节点保护用例；指令文本验收与真实效果分开。无占位生产接口、新依赖、预算增加或自动重评。用户已确认执行，内联流程与当前权限一致。
