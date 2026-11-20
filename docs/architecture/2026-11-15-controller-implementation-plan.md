# Unified Research Runtime Implementation Plan

> **For agentic workers:** Execute inline in this session, task by task with failing tests, implementation, and review. No delegation required.

**Goal:** 将现有 controller 库接成可恢复、约束完整、具备有限补读补查的统一研究内核，同时保持旧模式兼容。

**Architecture:** 复用已有规划、范围审查、证据评估、补查与 Writer。将单个异步循环拆成持久化任务节点；Contract、Critic 和 Scheduler 只做内部校验与调度。生产配置选择 legacy/controller，默认 legacy，质量对比后再切默认。

**Status:** 2026-11-15：Task 1–8 已实施，最新全量后端验证 1606 passed、1 deselected、36 warnings，56.38 秒；原有 SDK 提示及偶发数据库线程退出警告仍存在。默认切换、真实模型对比及旧策略删除属于后续质量验收。`docs/superpowers/` 被仓库忽略，本文件为可入库的正式计划与实施记录。

**Tech Stack:** Python、Pydantic、LangGraph、现有 SQLAlchemy checkpoint 与预算账本、pytest。

**Spec:** `docs/architecture/2026-11-14-controller-refactor-design.md` 的“实施收敛”优先。

## Global Constraints

- 保留工作区已有未提交修改，不覆盖 HEAD 之外的工作。
- 不新增任务数据库；复用 checkpoint pending writes、工具 Ledger、持久化 RunBudget。
- 保持 workflow / plan_execute / multi_agent 对外模式与历史数据。
- 未实现的执行能力执行前拒绝；不静默当作 retrieve。
- 不宣称已经超过市场产品；真实质量评测与确定性离线测试分别记录。

### Task 1: 执行边界与可复现回归

**Files:** `backend/tests/research/test_runtime.py`，`backend/src/deeptrace/research/runtime.py`，新增 `research/execution.py`。

**Interfaces:** 消费 ResearchInput、PlanTask、ResearchContract、HarnessContext；产出 ResearchTopicOutcome。执行上下文保留 mode、constraints、全部 query seeds、授权原文、任务页数和调用上限。

- [x] 使用脚本执行器验证实际 ResearchTopicInput：约束与上下文未丢失、请求 mode 一致、第二 query 保留、max_pages 不超过任务上限。
- [x] 验证未实现 LOOP/COMPUTE 被拒绝、取消继续传播、普通错误只影响对应分支。
- [x] 运行 `uv run --no-sync pytest tests/research/test_runtime.py -q`，确认测试因现有行为失败。
- [x] 实现统一执行边界，复用 validated_branch_context 与总预算 Gateway；再次运行上述测试。

### Task 2: 可恢复研究循环与版本化补查

**Files:** `research/runtime.py`、新增 `research/state.py`、`research/adapters.py`、`tests/research/test_runtime.py`。

**Interfaces:** `build_controller_research_graph(topic_graph, mode=..., max_tasks=..., max_parallel=..., max_rounds=..., checkpointer=None)`；保留 `run_controller_research` 独立调用接口。状态保存 contract、plan、plan_history、task_results、验证结果和现有 recovery 通道。

- [x] 添加真实脚本模型+证据存储回归：计划到验证实际执行，部分失败保留成功证据；补查 revision 递增且只包含未覆盖的新工作。
- [x] 添加 SQLite checkpoint 中断恢复回归：已完成分支不重新调用，未完成分支恢复，重新构建 graph 后仍可恢复。
- [x] 添加低预算、无进展、取消及必要任务未完成不能报 completed 的测试，运行并确认失败。
- [x] 将局部异步循环替换为 plan / dispatch / execute_task / evaluate / recover / reread / prepare_search / revise / finalize 图节点，使用 task_results 字典 reducer 保存分支输出。
- [x] 复用 build_plan_queries_node、run_evidence_evaluation 与现有补查协议，恢复通过上游 checkpointer 继承，所有子图调用传递 config/context。
- [x] 执行 `uv run --no-sync pytest tests/research tests/strategies/workflow tests/integration/test_recovery.py -q`。

### Task 3: 生产配置与三模式兼容接入

**Files:** `config/settings.py`、`application/assembly.py`、`backend/.env.example`、`tests/config/test_settings.py`、`tests/application/test_batch_assembly.py`、`tests/integration/test_controller_runtime.py`。

**Interfaces:** `Settings.research_orchestrator`，环境变量 `DEEPTRACE_RESEARCH_ORCHESTRATOR=legacy|controller`；默认 legacy，controller 返回 mode 与注册模式一致。

- [x] 添加配置非法值拒绝与三个模式通过真实 Harness/Writer 完成调用的测试；controller 不能在 Writer 失败时把回合标为 completed。
- [x] 运行上述测试确认缺失入口导致失败，然后添加配置和统一策略注册。
- [x] 使用生产 assembly 的 Runtime 与真实 checkpoint 验证注册，不绕过 API/Worker 共用的装配。
- [x] 执行 `uv run --no-sync pytest tests/config tests/application tests/integration -q`。

### Task 4: 边界校验与完成规则

**Files:** `research/critic.py`、`research/controller.py`、`research/contract.py`、`harness/graph.py`，对应 research/harness 测试。

**Interfaces:** Review 绑定 plan_id、revision、contract_revision 与计划内容摘要；Contract 使用生产 Gateway 已加载的预算快照；图定案需非空回答与通过的研究验证。

- [x] 添加同 revision 不同计划冒用 Review、空白回答误报完成、任务未完成和预算快照不一致的回归，确认失败后实现。
- [x] 不改变旧 checkpoint 的既有类型结构；新增字段保留旧反序列化默认值，新生成 Review 则必须经过一致性检查。
- [x] 执行 `uv run --no-sync pytest tests/research tests/harness tests/runtime -q`。

### Task 5: 验收、审查与文档

**Files:** `docs/architecture/target-architecture.md`、本方案、`backend/README.md`。

- [x] 全量执行 `uv run --no-sync pytest -m "not real" -q`，记录实际结果和现有警告。
- [x] 使用 code-review-and-quality 技能审查改动，按问题补回归并修复；不进行未授权合并。
- [x] 更新已实现能力、配置切换方式、恢复边界与未完成的真实质量评测，不用现有单元测试数代表产品效果。
- [x] 默认切换与旧策略删除等待同题评测证据，保留本轮可用的 controller 路径。

### Task 6: 补齐契约与新运行隔离

**Files:** `domain/coverage.py`、`research/runtime.py`、`research/state.py`、对应 contract/runtime 测试。

- [x] 先复现契约内需求可被原地改写，以及相同 checkpoint thread 的新运行复用旧任务的问题。
- [x] 将 ResearchRequirement 定义为不可变值对象，保留原序列化字段与旧记录兼容。
- [x] 初始化新研究时重置本次运行专属通道，恢复调用保持既有成功任务；保留调用方传入的会话上下文与授权证据。
- [x] 验证独立持久化图的新运行隔离、旧运行恢复及生产多轮会话。

### Task 7: 收敛计划构建与补查职责

**Files:** `research/adapters.py`、新增 `research/planning.py`、`research/runtime.py`、对应 adapter/runtime 测试。

- [x] 添加目标映射非法/重复、补查只承担指定缺口、失败任务替换及计划历史不变的回归。
- [x] 提取独立的任务构建函数；补查直接基于原 Contract 创建新 revision，不再临时创建新 Contract 或先补齐全部需求再覆盖字段。
- [x] 将初始规划与修订构建移到 planning 模块，runtime 只保留图控制流与节点调用。
- [x] 运行研究与生产集成测试，确认预算、模式及证据策略不回退。
- [x] 修复合法 128 字符 run_id 生成超长 plan_id 的边界问题；超长身份使用确定性摘要，保留完整 run_id，避免截断冲突。

### Task 8: 评测可追溯与最终验收

**Files:** `evaluation/__main__.py`、`tests/evaluation/test_langsmith.py`、架构及评测文档。

- [x] 先验证 CLI 能显式选择 legacy/controller，且实际装配配置和实验 metadata 一致；测试替代远端模型与上传，不调用外部服务。
- [x] 实验名和 metadata 记录实际编排器，保留环境变量默认行为与数据版本参数。
- [x] 全量后端离线回归、代码审查与文档同步；真实模型同题质量评测及默认切换仍独立记录。
