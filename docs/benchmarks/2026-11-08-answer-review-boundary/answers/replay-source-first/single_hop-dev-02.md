# single_hop-dev-02

Using only the frozen documentation, what prerequisites are required to pause a LangGraph workflow with interrupt()?

Component status: completed; error: None; new Provider calls: 1.

使用 `interrupt()` 暂停 LangGraph 工作流需要以下前提条件：

1. **一个 checkpointer**，用于持久化图状态；生产环境应使用持久化的 checkpointer[1]。checkpointer 是 human-in-the-loop 工作流所必需的，因为人需要能在任意时点查看图状态，并且图必须能在人更新状态后恢复执行[2]。
2. **config 中指定 thread ID**，让运行时知道从哪个状态恢复[1]。调用带 checkpointer 的图时，**必须**在 config 的 `configurable` 部分指定 `thread_id`[2]。checkpointer 以 `thread_id` 作为存储和检索 checkpoint 的主键；没有它，checkpointer 无法保存状态，也无法在 interrupt 后恢复执行[2]。
3. **在希望暂停的位置调用 `interrupt()`**，其 payload 必须可 JSON 序列化[1]。

补充说明：触发 interrupt 时，LangGraph 会通过其持久化层保存图状态，并无限期等待直到你恢复执行[1]。`thread_id` 实际上就是持久游标：复用它会恢复同一 checkpoint，使用新值则会以空状态开启全新线程[1]。

Unresolved gaps: []
