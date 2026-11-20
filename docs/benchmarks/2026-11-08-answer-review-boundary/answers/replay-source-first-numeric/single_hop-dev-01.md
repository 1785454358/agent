# single_hop-dev-01

Using only the frozen documentation, at what boundary does a LangGraph checkpointer create full state snapshots, and why must a thread_id be supplied?

Component status: completed; error: None; new Provider calls: 1.

结论：LangGraph 在每个 super-step 边界创建完整状态快照；thread_id 必须提供，因为检查点器以它为存储和检索检查点的主键，缺少它就无法保存状态或中断后恢复执行。

依据：
- 检查点器在每个 super-step 保存图状态快照，并按线程组织[1]。
- LangGraph 在每个 super-step 边界创建检查点；super-step 是图中一次“tick”，该步调度的所有节点执行（可能并行）。例如 START -> A -> B -> END 会在输入、节点 A、节点 B 各产生一个检查点[1]。
- 除 super-step 检查点外，还会在节点（任务）级持久化写入：同一 super-step 内每个节点完成时，其输出作为任务条目写入 checkpoint_writes 表，关联到进行中的检查点；这些逐任务写入用于 pending writes 恢复，若同一步另一节点失败，成功节点的写入已持久化，恢复时无需重跑；完整状态快照在 super-step 完成后才提交[1]。
- 这些任务写入不是完整 StateSnapshot 检查点，因此时间旅行从 super-step 边界的完整检查点恢复[1]。
- 使用检查点器调用图时，必须在 config 的 configurable 部分指定 thread_id[1]。
- 检查点器以 thread_id 作为存储和检索检查点的主键；没有它，检查点器无法保存状态，也无法在中断后恢复执行，因为它用 thread_id 加载已保存状态[1]。
- 默认情况下，检查点器在每个 super-step 写入每个状态通道的完整值[1]。

Unresolved gaps: []
