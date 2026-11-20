# conflicting_evidence-dev-02

Using only the frozen documentation, reconcile super-step checkpoint boundaries with durable per-task writes that avoid rerunning successful sibling nodes after a failure.

Component status: completed; error: None; new Provider calls: 1.

LangGraph 在每个 super-step 边界创建检查点：super-step 是图的一次“tick”，该步调度的所有节点（可能并行）执行，因此顺序图 START→A→B→END 在输入、A、B 各产生一个检查点，且只能从检查点（即 super-step 边界）恢复执行[1]。与此同时，除 super-step 检查点外，LangGraph 还在节点（任务）级别持久化写入：super-step 内每个节点完成时，其输出作为任务条目写入检查点器的 `checkpoint_writes` 表，并关联到进行中的检查点；这些 per-task 写入正是 pending writes 恢复的基础——若同一 super-step 中另一节点失败，已成功节点的写入已经持久化，恢复时无需重跑[1]。完整状态快照则在 super-step 完成后才提交[1]。持久化层由两张表支撑：Checkpoints 表每个 superstep 一行，存序列化图状态并链接父检查点；Writes 表每个 superstep 内每个节点输出一行，存 `(task_id, channel, value)` 元组并关联检查点；`put` 写检查点行，`put_writes` 写节点输出行[1]。因此二者可协调为：边界级检查点用于时间旅行与整体恢复，任务级写入用于故障时避免重算成功兄弟节点；这些任务写入不是完整 `StateSnapshot` 检查点，时间旅行仍从 super-step 边界的完整检查点恢复[1]。

Unresolved gaps: []
