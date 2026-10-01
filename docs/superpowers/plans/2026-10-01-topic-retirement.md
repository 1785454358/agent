# Research Executor Unification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 迁移测试到真实共享 Agent Loop，退出旧 Topic 执行实现和公开入口。

**Architecture:** 保留三种策略与领域契约。测试只替换外部模型、搜索和抓取，正式 Gateway、Executor、证据存储及 Checkpoint 继续执行。

**Tech Stack:** Python、pytest-asyncio、LangGraph、现有 ToolGateway 和 SQLite saver。

**Spec:** `docs/superpowers/specs/2026-10-01-topic-retirement-design.md`（用户 2026-10-01 回复“开始”，确认方案与删除清单）。

## Global Constraints

- 本次不改记忆生命周期、数据库、Provider 协议、依赖版本或前端。
- 不将旧执行图复制到测试目录，也不新增执行框架。
- 旧 Python 导入不保留兼容转发；不承诺旧 Topic 快照自动恢复，不删除持久化数据。
- 保留用户已有未提交修改，只显式暂存本任务文件。
- 当前没有上述执行子技能或子代理工具：在本会话按步骤执行与审查。用户已要求开始，采用 Inline Execution，不再为执行方式重复暂停。
- 命令从 `backend` 执行，用 `.venv/Scripts/python.exe -m pytest`；不修改依赖。

## 文件职责

- `backend/tests/strategies/fixtures.py`：共用角色脚本模型；研究响应只由本分支消息历史推导。
- `backend/tests/strategies/workflow/test_graph.py`、`plan_execute/test_graph.py`、`multi_agent/test_graph.py`：验证真实 Executor 下策略调度、部分失败和计划约束。
- `backend/tests/harness/test_workflow_response_slice.py`、`backend/tests/integration/test_workflow_response_exit_gate.py`、`test_recovery.py`、`test_mode_evaluation.py`：正式执行路径的响应、恢复与成本覆盖。
- `backend/tests/harness/test_agent_executor.py`：接收旧图的安全、页数、失败与正文隐私行为测试。
- `backend/tests/domain/test_research.py`：接收仍有效的 Topic 领域契约测试。
- `backend/src/deeptrace/strategies/__init__.py`：删除旧构图函数导出。
- 删除经确认的 `backend/src/deeptrace/strategies/topic/{__init__,graph,nodes,state}.py` 与覆盖已迁走的 `backend/tests/strategies/topic/{__init__,test_graph,test_state}.py`。
- `docs/architecture/agent-harness.md`：记录唯一入口与迁移限制。

### Task 1: 测试模型与生产路径覆盖

**Interfaces:** `ScriptedModelGateway(responses: dict[str, Any])` 提供 `invoke(*, role, messages, tools=None)`；`scripted_research_response(messages, tools)` 返回真实 `AIMessage`。策略角色的 callable 输入保持 prompt 字符串。

- [ ] 在 Workflow 正常完成测试中要求真实研究角色出现，并要求六次 researcher 调用（两个分支各 search、fetch、finish），先运行旧图观察失败。

```python
roles = [role for role, _ in model.calls]
assert roles.count("researcher") == 6
assert [r for r in roles if r != "researcher"] == ["planner", "evaluator"]
```

Run: `.venv/Scripts/python.exe -m pytest tests/strategies/workflow/test_graph.py::test_workflow_routes_plan_topics_evaluate_finalize -q`

- [ ] 在 fixture 中实现无全局研究游标的响应脚本：没有 ToolMessage 时从 HumanMessage 的“当前研究分支：”取查询；收到 search 结果时返回其中 URL 的 fetch tool calls；收到 fetch 后返回结束消息；空或无法解析的结果结束，由真实 Policy 判定 partial。

```python
return AIMessage(content="", tool_calls=[
    {"name": "search_web", "args": {"query": query}, "id": "search"}
])
```

工具定义必须包含 search_web、fetch_page；脚本不做授权、安全检查或页数截断。默认未配置 researcher 的角色网关调用此脚本，其他角色仍读取明确 responses。

- [ ] 迁移 Workflow 正常完成用例构图至 `build_research_agent_graph()`，运行上述测试及共享 Executor 用例，确认 green。
- [ ] 补充 Executor 覆盖：租户和模式 caller、超额 fetch 被 max_pages 阻止、非法和重复 URL、部分失败保留证据、fatal 停止、异常搜索预览、无正文检查点。用手工 AIMessage 队列驱动，保留真实 Gateway。

```python
assert fixture.fetcher.calls == ["https://example.com/a", "https://example.com/b"]
assert len(outcome.evidence_ids) == 2
assert "page_limit" in str(raw["messages"])
```

已有真实行为不人为制造红灯；这是给已存在实现补迁移覆盖。生产删除必须在该覆盖 green 后进行。

- [ ] Run: `.venv/Scripts/python.exe -m pytest tests/harness/test_agent_executor.py tests/harness/test_agent_invariants.py -q`。
- [ ] 审查 fixture 不复制生产算法、并发分支独立，然后显式提交 fixture 与本任务测试。

### Task 2: 迁移策略、Harness 与恢复消费者

**Interfaces:** 共用 Task 1 的角色模型和真实 `build_research_agent_graph()`；CrashOnceModelGateway 保留故障角色逻辑，支持 `tools` 并将 researcher 委托给无状态研究脚本。

- [ ] 在三种策略和响应切片文件移除重复 ScriptedModelGateway，改导入 fixture；旧构图调用改为真实 Executor。

```python
from deeptrace.harness.agent_executor import build_research_agent_graph
from strategies.fixtures import ScriptedModelGateway, build_gateway_fixture
graph = build_workflow_research_graph(build_research_agent_graph())
```

- [ ] 对有意的语义变化精确修改断言：空搜索通过 completion_nudge_limit 达到 incomplete_plan；仍无证据的整次策略保持 no_sources；部分研究 fatal 不再被 evaluator 标成 completed，而保留 tool_error 与兄弟证据。普通策略异常包装测试继续验证局部失败语义。
- [ ] 所有 role 计数纳入 researcher，不通过过滤掩盖执行失败；正常成功场景明确检查六次或三次研究模型调用。
- [ ] 将恢复、exit gate、mode evaluation 的图迁到真实 Executor；研究模型收到 tools 时返回脚本消息，角色日志继续计数。更新研究成本基线到包含三个 researcher 调用。

```python
assert row["model_calls"] == 6  # plan/supervisor + research*3 + evaluate + respond
assert row["tool_calls"] == 2
```

- [ ] Run: `.venv/Scripts/python.exe -m pytest tests/strategies/workflow tests/strategies/plan_execute tests/strategies/multi_agent tests/harness/test_workflow_response_slice.py tests/integration/test_workflow_response_exit_gate.py tests/integration/test_recovery.py tests/integration/test_mode_evaluation.py -q`。
- [ ] 审查持久化恢复仍验证 provider 不重复、账本与 evidence 实际生效，故障路径不靠替身结果通过。显式提交消费者迁移。

### Task 3: 删除旧实现并完成验收

**Interfaces:** 领域 `ResearchTopicInput` / `ResearchTopicOutcome` / `TopicStepError` 不变；唯一执行构图入口来自 Harness。

- [ ] 将旧 test_state 中输入验证、重复引用、错误约束、严格序列化四个测试迁到 domain/test_research，保留手工预期；删除旧 reducer 和注解结构测试。
- [ ] Run: `.venv/Scripts/python.exe -m pytest tests/domain/test_research.py tests/harness/test_agent_executor.py -q`。
- [ ] 用 `rg -n 'build_research_topic_graph|deeptrace.strategies.topic' backend/src backend/tests` 核对只余待删除的旧定义、导出和旧测试；删除文件采用 apply_patch。
- [ ] 移除 strategies/__init__.py 旧导出，并以 apply_patch 删除确认的七个文件。其他策略的同名 reducer 保留。
- [ ] 在架构文档说明新入口、工具定义 researcher 需求、旧 Python 导入不兼容及旧快照恢复限制。
- [ ] Run: `.venv/Scripts/python.exe -m pytest -m "not real" -q`；再检查修改文件 Ruff（源全规则，测试 I/F）、格式与 diff。修改文件数量只指本任务，不包含用户引用 / 评测改动。
- [ ] 复核覆盖迁移、代码净减少、没有新框架；显式暂存并提交旧实现退出与文档。勾选实际完成的步骤，记录测试结果，不将未运行真实 API 说成已验证。

## 实际验收

执行完成时记录各阶段命令结果、删除行数与覆盖迁移差异。
