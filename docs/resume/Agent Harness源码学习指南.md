# Agent Harness 源码学习指南

目标不是逐文件背代码，而是沿一轮请求回答四个问题：谁决定下一步、哪些状态可恢复、外部调用在哪里发生、失败后由谁处理。

## 推荐阅读顺序

### 1. 先看领域契约

- [研究输入与输出](../../backend/src/deeptrace/domain/research.py)
- [AgentOutcome](../../backend/src/deeptrace/domain/agent.py)
- [工具请求与结果](../../backend/src/deeptrace/domain/tools.py)
- [错误分类](../../backend/src/deeptrace/domain/errors.py)

先确认 `ResearchInput → ResearchOutcome`、`ToolRequest → ToolResult` 和 `AgentOutcome` 的字段。后续所有 Graph 和 Gateway 都在实现这些契约。

自测：为什么 `AgentOutcome` 同时需要 `status`、`stop_reason`、`errors` 和 `unfinished_todos`？

### 2. 看 Session Graph

入口是 [harness/graph.py](../../backend/src/deeptrace/harness/graph.py)。按下面的顺序跟踪：

```text
initialize_turn
→ manage_context
→ classify_intent
→ recall_memory
→ strategy / direct response / memory update
→ consolidate_memory
→ select_response_mode
→ finalize_turn
```

重点区分：

- `HarnessState` 是可恢复会话状态；
- `HarnessContext` 是运行时依赖；
- `StrategyRegistry` 和 `ResponseGraphRegistry` 隔离具体子图；
- 顶层只接受标准 Outcome，不读取策略私有 State。

自测：为什么模型实例、数据库连接和时钟不应该进入 Checkpoint？

### 3. 看三种 strategy 如何共享执行器

依次阅读：

- [Workflow nodes](../../backend/src/deeptrace/strategies/workflow/nodes.py)
- [Plan-and-Execute nodes](../../backend/src/deeptrace/strategies/plan_execute/nodes.py)
- [Multi-Agent nodes](../../backend/src/deeptrace/strategies/multi_agent/nodes.py)

搜索 `topic_graph.ainvoke`，观察三种策略怎样把一个研究分支交给同一个 Agent Graph，再把 `ResearchTopicOutcome` 合并成各自的 `ResearchOutcome`。

关注差异：Workflow 固定推进，Plan-and-Execute 有评估与有界重规划，Multi-Agent 用独立 Researcher 分支并行执行。不要把差异误写成三套工具调用实现。

### 4. 读 Shared Agent Loop

核心文件：

- [agent_executor.py](../../backend/src/deeptrace/harness/agent_executor.py)
- [agent_state.py](../../backend/src/deeptrace/harness/agent_state.py)
- [agent_tools.py](../../backend/src/deeptrace/harness/agent_tools.py)
- [execution.py](../../backend/src/deeptrace/harness/policies/execution.py)

沿节点阅读：

```text
prepare_context → call_model → execute_tools / observe
                ↑                         ↓
                └──── nudge / next round ─┘
                                  ↓
                               finalize
```

检查以下细节：

1. `prepare_context` 在调用模型前先执行停止判断；
2. `call_model` 只通过 `runtime.context.model_gateway.invoke`；
3. tool call ID 在持久化前被规范化，重放时保持稳定；
4. `execute_batch` 区分本地 `write_todos` 和外部工具；
5. `observe` 与 `ExecutionPolicy` 决定继续、提示或退出；
6. `finalize` 总是构造 Outcome。

自测：模型在仍有未完成 Todo 时直接返回文本，循环为什么不会立即当作 completed？

### 5. 读上下文和模型边界

- [Agent Context Policy](../../backend/src/deeptrace/harness/policies/agent_context.py)
- [Prompt envelope](../../backend/src/deeptrace/harness/prompts.py)
- [ModelGateway](../../backend/src/deeptrace/harness/model_gateway.py)
- [Token budget](../../backend/src/deeptrace/harness/token_budget.py)

画出两层防线：Context Policy 负责构造和裁剪，ModelGateway 在 Provider 边界验证 system instruction、original task、current constraints。再检查工具交换为何必须整组保留。

自测：如果保留了 assistant tool call，却裁掉对应 ToolMessage，会导致什么协议问题？

### 6. 读工具治理和证据流

- [Agent tool dispatch](../../backend/src/deeptrace/harness/agent_tools.py)
- [ToolGateway](../../backend/src/deeptrace/tools/gateway.py)
- [Tool policy](../../backend/src/deeptrace/tools/policy.py)
- [Evidence Store](../../backend/src/deeptrace/tools/evidence_store.py)
- [Execution Ledger](../../backend/src/deeptrace/persistence/execution_ledger.py)

从 `execute_batch` 跟到 `ToolGateway.execute`，记录下执行顺序：调用协议校验、URL 授权、预算、Ledger、缓存/Singleflight、Provider、Evidence、结果提交。具体顺序以源码为准，不靠文档记忆。

然后阅读同批依赖处理：无依赖调用有界并行；fetch 如果依赖本批 search 的结果则等待；最终 ToolMessage 仍按原调用顺序合并。

自测：为什么并发完成顺序不能直接成为 ToolMessage 顺序？

### 7. 读 Checkpoint 与恢复

- [Checkpoint serializer](../../backend/src/deeptrace/harness/checkpoint.py)
- [SQL Checkpointer](../../backend/src/deeptrace/persistence/checkpoint.py)
- [Execution Ledger](../../backend/src/deeptrace/persistence/execution_ledger.py)
- [Worker](../../backend/src/deeptrace/worker/)

区分三个时间点：Provider 未调用、Provider 已返回但 Ledger 未提交、Ledger 已提交但节点 Checkpoint 未落盘。最后一种可以通过 Ledger 重放避免再次调用；中间窗口仍可能重复，因此系统不声称 exactly-once。

自测：为什么工具节点之后单独设置 Checkpoint 边界有价值？

### 8. 读记忆生命周期

- [Memory lifecycle](../../backend/src/deeptrace/harness/memory/lifecycle.py)
- [Recall policy](../../backend/src/deeptrace/harness/memory/recall.py)
- [Write policy](../../backend/src/deeptrace/harness/memory/write.py)
- [Retriever](../../backend/src/deeptrace/harness/memory/retriever.py)
- [Memory Store](../../backend/src/deeptrace/persistence/memory_store.py)
- [Chroma index](../../backend/src/deeptrace/persistence/chroma_memory.py)

按“何时存、存什么、如何组织、何时召回、如何更新、如何遗忘”六个问题检查实现。MySQL/SQLite 是权威记录，向量库是检索索引；索引失败不能使已经写入权威 Store 的事实消失。

自测：为什么长期记忆召回结果属于可裁剪背景，而不是当前约束？

## 用测试验证理解

先运行 Harness 重点测试：

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest `
  tests/harness/test_agent_executor.py `
  tests/harness/test_agent_invariants.py `
  tests/harness/test_model_gateway.py `
  tests/harness/memory/test_lifecycle.py -q
```

再运行全部离线测试：

```powershell
.\.venv\Scripts\python.exe -m pytest -m "not real" -q
```

当前记录基线为 `464 passed, 1 deselected`。如果代码继续变化，以新运行结果为准。

建议重点阅读这些测试场景：

- 每种策略的模型调用都包含 system、original task、constraints；
- 每个 tool call 都有 ToolMessage；
- 外部工具和模型分别经过对应 Gateway；
- 所有受控退出都有 AgentOutcome；
- Checkpoint 恢复后上述不变量仍成立；
- 无依赖工具并行、依赖 fetch 等待 search，并保持结果顺序；
- Ledger 重放不重复调用 Provider。

## 源码讲解模板

面试时每个模块按三句话讲：

1. **问题**：这个模块防止什么失败或混乱？
2. **机制**：主要输入、输出和核心函数是什么？
3. **边界**：它不负责什么，失败由哪一层接手？

例如 ToolGateway：它解决外部能力调用缺乏统一权限、预算和幂等的问题；输入是 `ToolRequest`，输出是 `ToolResult`；语义修复不由 Gateway 做，而是由 Agent Loop 读取失败 ToolMessage 后决定下一步。
