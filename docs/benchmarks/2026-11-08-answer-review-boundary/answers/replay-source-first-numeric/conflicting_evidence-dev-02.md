# conflicting_evidence-dev-02

Using only the frozen documentation, reconcile super-step checkpoint boundaries with durable per-task writes that avoid rerunning successful sibling nodes after a failure.

Component status: completed; error: None; new Provider calls: 1.

结论：两者可以协调，因为 LangGraph 的持久化分两层：完整状态快照只在 super-step 边界提交，而同一 super-step 内每个节点（任务）的输出在节点完成时即写入 `checkpoint_writes` 表，作为关联到进行中检查点的任务条目；因此同一步中某节点失败后，已成功兄弟节点的写入已持久化，恢复时无需重跑它们[1]。

具体机制：
1. 检查点边界：LangGraph 在每个 super-step 边界创建检查点；super-step 是图中所有被调度节点执行（可能并行）的一个“tick”，只能从检查点（即 super-step 边界）恢复执行[1]。
2. 任务级写入：除 super-step 检查点外，LangGraph 还在节点（任务）级别持久化写入；super-step 内每个节点完成时，其输出作为任务条目写入检查点器的 `checkpoint_writes` 表，并链接到进行中的检查点[1]。
3. 恢复效果：这些 per-task 写入正是 pending writes 恢复的基础——若同一 super-step 中另一节点失败，成功节点的写入已经持久化，恢复时无需重跑[1]。完整状态快照则在 super-step 完成后才提交[1]。
4. 存储抽象对应：检查点表每个 superstep 一行，存序列化图状态并链接父检查点；写入表每个 superstep 内每个节点输出一行，存 `(task_id, channel, value)` 元组并链接到检查点；`put` 写检查点行，`put_writes` 写节点输出行[1]。
5. 边界含义：任务写入不是完整的 `StateSnapshot` 检查点，所以 time travel 仍从 super-step 边界的完整检查点恢复[1]。

因此，super-step 检查点决定“可恢复的完整状态边界”，per-task 写入决定“同一步内已完成兄弟节点不被重跑”；二者互补而非冲突[1]。

Unresolved gaps: []
