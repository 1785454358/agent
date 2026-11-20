# single_hop-dev-02 / plan_execute

Using only the frozen documentation, what prerequisites are required to pause a LangGraph workflow with interrupt()?

Status: completed; answered flag: True; response reason: None; model calls: 6; seconds: 34.118.

结论：按冻结文档，用 `interrupt()` 暂停 LangGraph 工作流需要三项前置条件：**checkpointer**、**config 中的 thread ID**、**在节点内调用 `interrupt()` 且 payload 可 JSON 序列化** [1]。此外，恢复时须用同一 thread ID 重新调用图并传入 `Command(resume=...)` [1]；若使用 interrupt 响应 schema，还需 `@langchain/langgraph` 1.4.16 或更高版本 [1]。

**1. checkpointer（持久化）**

文档明确列出使用 `interrupt()` 需要“A **checkpointer** to persist the graph state（生产环境应使用 durable checkpointer）” [1]。原因是 interrupt 触发时 LangGraph 通过持久化层保存图状态并等待恢复 [1]；checkpointer 在每一步保存状态快照，且 human-in-the-loop 工作流需要它来查看状态并在更新后恢复执行 [2]。图需以 checkpointer 编译，例如 `compile({ checkpointer })` [2][1]。

**2. thread ID**

调用图时必须在 `configurable` 部分提供 `thread_id` [2]。文档说明：使用 checkpointer 调用图时**必须**指定 `thread_id`；没有它，checkpointer 无法保存状态或在 interrupt 后恢复执行，因为它用 `thread_id` 加载已保存状态 [2]。`thread_id` 是持久化游标：复用同一值恢复同一 checkpoint，新值则开启空状态的新线程 [1]。恢复时也必须使用中断发生时相同的 thread ID [1]。

**3. 调用位置与恢复方式**

`interrupt()` 应在图的节点内调用，传入任意 JSON 可序列化的 payload，该值会返回给调用方 [1]。恢复时重新调用图并传入 `Command(resume=...)`，该值成为节点内 `interrupt()` 调用的返回值 [1]。

**4. 版本与编译**

interrupt 响应 schema 需要 `@langchain/langgraph` 1.4.16 或更高版本 [1]；示例显示图需以 checkpointer 编译后才能配合 thread_id 调用 [1]。

**最小顺序**：以 checkpointer 编译图 → 用含 `thread_id` 的 config 调用图 → 节点内执行到 `interrupt()` 暂停 → 用同一 config 和 `Command(resume=...)` 重新调用恢复 [2][1]。

**缺口说明**：本次可见材料未给出除上述版本外的其他最低版本、依赖或运行环境要求；不能据此推断全部文档没有此类要求。

## Sources

1. Interrupts — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/interrupts.mdx
2. Checkpointers — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/checkpointers.mdx
