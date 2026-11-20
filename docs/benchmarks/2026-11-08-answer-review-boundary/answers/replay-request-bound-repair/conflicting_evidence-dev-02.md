# conflicting_evidence-dev-02

Using only the frozen documentation, reconcile super-step checkpoint boundaries with durable per-task writes that avoid rerunning successful sibling nodes after a failure.

Component status: completed; error: None; new Provider calls: 1.

LangGraph 在每个 super-step 边界创建检查点，super-step 是图中所有该步被调度节点执行（可能并行）的一个“tick”；顺序图 START→A→B→END 会为输入、A、B 各产生一个检查点，且只能从检查点（即 super-step 边界）恢复执行[1]。与此同时，LangGraph 还在节点（任务）级别持久化写入：同一 super-step 内每个节点完成时，其输出作为任务条目写入检查器的 `checkpoint_writes` 表，并关联到进行中的检查点；这些按任务写入正是 pending writes 恢复的基础——若同一 super-step 中另一节点失败，已成功节点的写入已经持久化，恢复时无需重跑[1]。完整状态快照则在 super-step 完成后才提交[1]。因此两者可这样协调：super-step 检查点界定可恢复/时间旅行的边界，而任务级写入在边界内提供细粒度持久性；失败后从该 super-step 恢复时，成功兄弟节点的任务写入被复用，不重跑，只有失败或未完成的节点需要重新执行[1]。文档也明确这些任务写入不是完整 `StateSnapshot` 检查点，所以时间旅行仍从 super-step 边界的完整检查点恢复[1]。存储上对应两张表：检查点表每个 superstep 一行，写入表每个 superstep 内每个节点输出一行，由检查器同时管理 `put` 与 `put_writes`[1]。

Unresolved gaps: []
