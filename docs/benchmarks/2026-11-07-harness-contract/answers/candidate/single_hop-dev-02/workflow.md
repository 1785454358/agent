# single_hop-dev-02 / workflow

Using only the frozen documentation, what prerequisites are required to pause a LangGraph workflow with interrupt()?

Status: completed; answered: True; reason: None; model calls: 6; tools: 14; seconds: 31.691.

**结论：** 用 `interrupt()` 暂停 LangGraph 工作流，前提是图已配置 checkpointer，且调用时在 config 的 `configurable` 中提供 `thread_id` [1][2]。恢复时还需用相同 `thread_id` 再次调用，并以 `Command({ resume: ... })` 传回值 [1]。

**两个前提**

1. **配置 checkpointer。** 触发 interrupt 时，LangGraph 通过持久化层保存图状态并等待恢复 [1]；checkpointer 写入精确的图状态，以便之后恢复 [1]。checkpointer 也是 human-in-the-loop 工作流所需，因为人需要查看任意时刻的图状态，图也要能在状态更新后恢复执行 [2]。

2. **提供 `thread_id`。** 带 checkpointer 调用图时，**必须**在 config 的 `configurable` 部分指定 `thread_id` [2]，例如 `{"configurable": {"thread_id": "1"}}` [2]。checkpointer 以 `thread_id` 为主键存储和检索检查点；没有它，checkpointer 无法保存状态，也无法在 interrupt 后恢复执行 [2]。`thread_id` 相当于持久游标：复用同一值会恢复同一检查点，新值则开启空状态的新线程 [1]。

**恢复条件（与暂停配套）**

- 恢复时必须使用与 interrupt 发生时**相同的 thread ID** [1]。
- 通过 `Command(resume=...)` 把值传回 `interrupt()`；文档称这是唯一适合作为 `invoke()`/`stream()`/`stream_events()` 输入的 `Command` 模式 [1]。

**边界说明**

- 上述前提针对自建图。使用 Agent Server 时无需手动实现或配置 checkpointer/store，服务器在后台处理持久化基础设施 [3]；但该说明不改变自建图需配置 checkpointer 与 `thread_id` 的要求。
- 若使用 `MemorySaver`/`InMemorySaver`，检查点存于内存，进程重启即丢失；生产环境应改用持久化 checkpointer [3]。这是持久性选择，不是暂停本身的额外前提。
- 文档另提到 interrupt 响应 schema 需 `langgraph>=1.2.12`（Python）或 `@langchain/langgraph` 1.4.16 及以上（JS）[1]；这仅适用于使用响应 schema 的场景，不是所有 `interrupt()` 暂停的通用前提。

## Sources

1. Interrupts — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/interrupts.mdx
2. Checkpointers — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/checkpointers.mdx
3. Persistence — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/persistence.mdx
