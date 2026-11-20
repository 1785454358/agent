# conflicting_evidence-dev-02

Using only the frozen documentation, reconcile super-step checkpoint boundaries with durable per-task writes that avoid rerunning successful sibling nodes after a failure.

Component status: completed; error: None; new Provider calls: 1.

LangGraph 在每个 super-step 边界创建检查点，因此可恢复的完整状态快照以 super-step 为粒度；同时它也在节点（任务）级别持久化写入，从而避免同一 super-step 内失败后重跑已成功的兄弟节点。

具体机制：每个 super-step 中所有被调度的节点执行（可能并行）[1]。除 super-step 检查点外，LangGraph 还把写入持久化到节点（任务）级别：super-step 内每个节点完成时，其输出作为任务条目写入检查点的 `checkpoint_writes` 表，并关联到进行中的检查点[1]。这些按任务的写入正是 pending writes 恢复的基础：若同一 super-step 中另一个节点失败，已成功节点的写入已经持久化，恢复时无需重跑[1]。完整状态快照则在 super-step 完成后才提交[1]。

存储层对应两张表：检查点表每个 superstep 一行，保存序列化的图状态（`channel_values`、`channel_versions`、`versions_seen`）并链接父检查点；写入表每个 superstep 内每个节点输出一行，保存 `(task_id, channel, value)` 元组并关联到检查点；检查点管理器同时管理这两张表，`put` 写检查点行，`put_writes` 写节点输出行[1]。

故障容错语义：若某 superstep 有一个或多个节点失败，可从最后一个成功步骤重启图[1]。节点执行中途失败时，LangGraph 保存该 super-step 中其他已成功完成节点的 pending checkpoint writes；从该 super-step 恢复执行时不会重跑成功节点[1]。

边界区分：这些任务写入不是完整的 `StateSnapshot` 检查点，因此 time travel 仍从 super-step 边界的完整检查点恢复[1]。也就是说，per-task 写入用于同一 super-step 内的故障恢复，而可回放/分叉的恢复点仍是 super-step 检查点。

补充：协作式关闭会在当前 superstep 完成后停止运行并保存可恢复检查点，可用相同 `thread_id` 以 `invoke(None, config)`（Python）或 `invoke(null, config)`（JS）恢复[2]。

Unresolved gaps: []
