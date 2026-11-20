## 结论

在本次可见的官方材料范围内，可以确认：**checkpoint（checkpointer）是 LangGraph 的图状态持久化层**，在每个 superstep 保存图状态快照，支撑 human-in-the-loop、交互间记忆与持久执行 [1]；快照按 `thread_id` 组织，`thread_id` 必填，`checkpoint_id` 可选用于指向线程内某个快照 [1][2]。**interrupt 必须启用 checkpointer**，恢复时用同一 `thread_id` 的 config 调用 `Command(resume=...)` [3][4]。

但用户要求的 **Store/BaseStore 的用途、namespace 组织、跨线程共享机制，以及两者在进程重启、跨线程共享下的对比**，本次可见材料**没有覆盖**。因此下表只对 checkpoint 一侧给出有据内容，Store 一侧标为“无法确认”，不用常识补全。

## 比较表

| 维度 | Checkpoint | Store |
|---|---|---|
| 用途 | 图状态快照持久化，每个 superstep 保存状态，支持 HITL、交互间记忆、持久执行 [1][2] | 无法确认（可见材料未涉及 Store/BaseStore） |
| 组织维度 | 按 `thread_id` 组织；`thread_id` 必填，`checkpoint_id` 可选指向线程内某快照 [1][2] | 无法确认（namespace 机制未见） |
| 线程边界 | 一个 thread 是一系列 checkpoint，由唯一 `thread_id` 标识 [1][2] | 无法确认 |
| 进程重启恢复 | 事实：持久化后端（如 PostgresSaver）保留完整 checkpoint 历史 [2]；推断：用同一 `thread_id` 可重新加载，但原文未直接写“进程重启”场景 | 无法确认 |
| interrupt 恢复 | 事实：必须启用 checkpointer；恢复用同一 `thread_id` + `Command(resume=...)`；复用 `thread_id` 恢复同一 checkpoint，新值开新线程空状态 [3][4][5] | 无法确认 |
| 跨线程共享 | 事实：按线程隔离，不同 `thread_id` 是不同状态序列 [1][2]；是否可跨线程读取未明确 | 无法确认 |
| 适用场景 | 会话内状态、HITL 审批、失败续跑 [1][2][3] | 无法确认（材料仅泛称“跨会话长期记忆” [6][7]，未绑定到 Store） |

## 分场景说明

**进程重启**
- 事实：checkpointer 有 InMemorySaver（仅调试测试）、SqliteSaver（轻量演示）、PostgresSaver/AsyncPostgresSaver（生产、保留完整历史）等实现 [2]。
- 推断：只有持久化后端（如 Postgres）才能在进程重启后保留状态；InMemorySaver 随进程消失。此推断基于“内存 vs 数据库”的实现描述 [2]，原文未直接陈述重启行为。
- Store：无法确认。

**interrupt 恢复**
- 事实：`interrupt()` 在节点内暂停执行并保存图状态，需 checkpointer 持久化 [3][4]。
- 事实：恢复时用同一 `thread_id` 的 config 调用 `Command(resume=...)`；`thread_id` 是持久指针，复用恢复同一 checkpoint，新值开新线程空状态 [3][5]。
- 事实：恢复会从节点开头**重跑整个节点**，不是从 interrupt 那一行继续；节点内多个 interrupt 按调用顺序索引匹配 resume 值 [3][4]。
- 最小调用顺序：先 `graph.invoke(input, config={"configurable": {"thread_id": ...}})` 触发 interrupt 并暂停；再用同一 config 调用 `graph.invoke(Command(resume=...), config)` 恢复 [3][4]。

**跨线程共享**
- 事实：checkpoint 按线程隔离，不同 `thread_id` 对应不同状态序列 [1][2]。
- 无法确认：checkpoint 是否支持跨线程读取；Store 的跨线程共享机制与前提。

## 适用场景

- Checkpoint：会话内状态保持、HITL 审批暂停/恢复、失败后续跑（pending writes 避免重跑已完成节点）[1][2][3]。
- Store：无法确认（可见材料未涉及）。

## 来源

- [3] Interrupts - Docs by LangChain: https://docs.langchain.com/oss/python/langgraph/interrupts
- [2] checkpoints | langgraph | LangChain Reference: https://reference.langchain.com/python/langgraph/checkpoints
- [6] GitHub - langchain-ai/langgraph: https://github.com/langchain-ai/langgraph
- [4] interrupt | langgraph | LangChain Reference: https://reference.langchain.com/python/langgraph/types/interrupt
- [7] LangGraph overview - Docs by LangChain: https://docs.langchain.com/oss/python/langgraph/overview
- [5] Interrupts - Docs by LangChain (JS): https://docs.langchain.com/oss/javascript/langgraph/interrupts
- [1] langgraph.checkpoint | LangChain Reference: https://reference.langchain.com/python/langgraph/checkpoint
