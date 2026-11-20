# single_hop-dev-02 / workflow

Using only the frozen documentation, what prerequisites are required to pause a LangGraph workflow with interrupt()?

Status: completed; answered: True; reason: None; model calls: 6; tools: 20; seconds: 27.658.

结论：按冻结文档，用 `interrupt()` 暂停工作流需同时满足三项前置条件：配置 checkpointer、在 config 中提供 thread ID、在节点内调用且 payload 可 JSON 序列化 [1]。

- **checkpointer**：用于持久化图状态；生产环境应使用持久化 checkpointer [1]。文档把 checkpointer 列为使用 `interrupt` 的必要项 [1]，并说明中断时 LangGraph 通过持久化层保存状态 [1]。checkpointer 也是 human-in-the-loop 工作流所需，因为人需要能查看任意时刻的图状态，且图需在人更新状态后恢复执行 [2]。
- **thread ID**：必须在 config 的 `configurable` 中提供 `thread_id`，运行时据此知道从哪个状态恢复 [1]。带 checkpointer 调用图时，**必须**在 config 的 `configurable` 部分指定 `thread_id` [2]。checkpointer 以 `thread_id` 为主键存取检查点；没有它无法保存状态或在 interrupt 后恢复 [2]。
- **调用位置与 payload**：应在希望暂停的节点内调用 `interrupt()`，payload 必须可 JSON 序列化 [1]。恢复时用 `Command(resume=...)`，其值返回到 `interrupt()` 调用处 [1]；该模式是唯一可作为 `invoke()`/`stream()`/`stream_events()` 输入的 `Command` 模式 [1]。

版本条件：interrupt 响应 schema 需 `@langchain/langgraph` 1.4.16+（Python 侧为 `langgraph>=1.2.12`）[1]；这是该 schema 功能的条件，不是 `interrupt()` 本身的一般版本要求 [1]。本次可见材料未给出 `interrupt()` 本身的其他版本或依赖前置条件。

## Sources

1. Interrupts — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/interrupts.mdx
2. Checkpointers — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/checkpointers.mdx
