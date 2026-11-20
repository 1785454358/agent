# single_hop-dev-02

Using only the frozen documentation, what prerequisites are required to pause a LangGraph workflow with interrupt()?

Component status: completed; error: None; new Provider calls: 1.

根据冻结文档，使用 `interrupt()` 暂停 LangGraph 工作流需要三项前提：

1. **一个 checkpointer**，用于持久化图状态；文档建议生产环境使用持久型 checkpointer[1]。
2. **配置中的 thread ID**，让运行时知道从哪个状态恢复[1]。
3. **在希望暂停的位置调用 `interrupt()`**，且传入的 payload 必须可 JSON 序列化[1]。

补充支持条件：checkpointer 是 human-in-the-loop 工作流所必需的，因为人需要能查看任意时刻的图状态，且图必须能在人更新状态后恢复执行[2]；调用带 checkpointer 的图时，**必须**在 config 的 `configurable` 部分指定 `thread_id`[2]。checkpointer 以 `thread_id` 为主键存储和检索 checkpoint；没有它，checkpointer 无法保存状态，也无法在 interrupt 后恢复执行[2]。触发 interrupt 时，LangGraph 会用其持久化层保存图状态，并无限期等待恢复[1]。

Unresolved gaps: []
