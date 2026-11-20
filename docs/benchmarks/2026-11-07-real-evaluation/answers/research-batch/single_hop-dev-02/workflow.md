# single_hop-dev-02 / workflow

Using only the frozen documentation, what prerequisites are required to pause a LangGraph workflow with interrupt()?

Status: completed; answered flag: True; response reason: None; model calls: 6; seconds: 28.873.

**结论：** 冻结文档列出使用 `interrupt()` 暂停工作流的三项前置条件：配置 checkpointer 持久化图状态（生产环境用持久型）、在 config 中提供 `thread_id`、在希望暂停的位置调用 `interrupt()` 且 payload 可 JSON 序列化 [1]。

**逐项条件**

1. **Checkpointer**：`interrupt()` 触发时，LangGraph 通过持久化层保存图状态并无限期等待恢复 [1]；checkpointer 正是用于 human-in-the-loop 这类需查看状态并在更新后恢复执行的场景 [2]。生产环境应使用持久型 checkpointer，`MemorySaver`/`InMemorySaver` 存于内存，进程重启即丢失 [3]。
2. **thread_id**：运行时靠它知道从哪个状态恢复 [1]。checkpointer 以 `thread_id` 为主键存取检查点；没有它，checkpointer 无法保存状态，也无法在 interrupt 后恢复执行 [2]。`thread_id` 相当于持久游标：复用同一值恢复同一检查点，用新值则开启空状态的新线程 [1]；恢复时必须使用中断发生时相同的 thread ID [1]。
3. **调用位置与 payload**：`interrupt()` 须写在希望暂停的节点位置，payload 必须可 JSON 序列化 [1]。恢复时通过 `Command(resume=...)` 把值返回给 `interrupt()`，且这是唯一适合作为 `invoke()`/`stream()` 输入的 Command 模式 [1]。

**其他边界**

- 响应模式（response schema）需 `langgraph>=1.2.12`（Python）/ `@langchain/langgraph` 1.4.16 及以上（JS）[1]；这只是可选类型化恢复值的版本下限，不是暂停本身的前提。
- 使用 Agent Server 时无需手动配置 checkpointer 或 store，服务器自动处理持久化 [3]。
- 中断后节点恢复会重跑该节点，若 `interrupt()` 之前已有副作用（如写记录），可能重复执行 [1]。

**缺口说明：** 本次可见材料未涉及编译图时除 checkpointer 外的其他参数要求，也未列出不支持的环境；上述范围仅限当前可见文档。

## Sources

1. Interrupts — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/interrupts.mdx
2. Checkpointers — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/checkpointers.mdx
3. Persistence — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/persistence.mdx
