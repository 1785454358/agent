# single_hop-dev-02

Using only the frozen documentation, what prerequisites are required to pause a LangGraph workflow with interrupt()?

Component status: completed; error: None; new Provider calls: 1.

根据冻结文档，使用 `interrupt()` 暂停 LangGraph 工作流需要三项前提：

1. **一个 checkpointer**，用于持久化图状态；生产环境应使用持久型 checkpointer[1]。文档说明 interrupt 触发时 LangGraph 会通过其持久化层保存图状态并等待恢复[1]，而 checkpointer 正是用于保存状态、使图能在人工更新状态后恢复执行[2]。
2. **配置中的 thread ID**，让运行时知道从哪个状态恢复[1]。checkpointer 以 `thread_id` 作为存储和检索 checkpoint 的主键；没有它，checkpointer 无法保存状态，也无法在 interrupt 后恢复执行[2]。
3. **在希望暂停的位置调用 `interrupt()`**，且其 payload 必须可 JSON 序列化[1]。

补充说明：`interrupt()` 在节点内调用时，LangGraph 通过抛出异常来挂起执行，运行时捕获该异常后保存当前状态并等待外部输入[1]。

Unresolved gaps: []
