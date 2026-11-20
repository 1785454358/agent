# single_hop-dev-01

Using only the frozen documentation, at what boundary does a LangGraph checkpointer create full state snapshots, and why must a thread_id be supplied?

Component status: completed; error: None; new Provider calls: 1.

LangGraph 在每个 super-step 边界创建完整状态快照（checkpoint）[1]。super-step 是图的一次“tick”，该步调度的所有节点（可能并行）执行；例如 `START -> A -> B -> END` 在输入、节点 A、节点 B 各自形成独立 super-step，并在每一步之后产生一个 checkpoint[1]。此外，节点（任务）级写入也会持久化到 `checkpoint_writes` 表，但这些是按任务写入，不是完整 `StateSnapshot` checkpoint；完整状态快照在该 super-step 完成时提交[1]。因此时间旅行只能从 super-step 边界的完整 checkpoint 恢复[1]。

必须提供 `thread_id`：调用带 checkpointer 的图时，必须在 config 的 `configurable` 部分指定 `thread_id`[1]。checkpointer 以 `thread_id` 作为存储和检索 checkpoint 的主键；没有它，checkpointer 无法保存状态，也无法在 interrupt 后恢复执行，因为它用 `thread_id` 加载已保存状态[1]。

Unresolved gaps: []
