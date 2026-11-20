# single_hop-dev-02

Using only the frozen documentation, what prerequisites are required to pause a LangGraph workflow with interrupt()?

Component status: completed; error: None; new Provider calls: 1.

使用冻结文档回答：用 `interrupt()` 暂停 LangGraph 工作流需要三项前提[1]：1) 一个 **checkpointer** 用于持久化图状态，生产环境应使用持久化 checkpointer[1]；2) 配置中提供 **thread ID**，使运行时知道从哪个状态恢复[1]；3) 在希望暂停的位置调用 `interrupt()`，且其 payload 必须可 JSON 序列化[1]。

补充依据：checkpointer 是 human-in-the-loop 工作流所必需的，因为人需要能查看任意时刻的图状态，图也需要在人更新状态后恢复执行[2]；checkpointer 以 `thread_id` 为主键存储和检索 checkpoint，没有它就无法保存状态或在 interrupt 后恢复执行[2]；调用带 checkpointer 的图时，**必须**在 config 的 `configurable` 部分指定 `thread_id`[2]。触发 interrupt 时，LangGraph 使用其持久化层保存图状态，并无限期等待恢复[1]；`thread_id` 实际是持久游标，复用它会恢复同一 checkpoint，使用新值则开启空状态的新线程[1]。

注意：上述三项是使用 `interrupt()` 的前提；若使用 Agent Server，持久化由服务器自动处理，无需手动实现或配置 checkpointer/store[3]，但这不改变 `interrupt()` 本身对 thread ID 与调用位置的要求[1]。

Unresolved gaps: []
