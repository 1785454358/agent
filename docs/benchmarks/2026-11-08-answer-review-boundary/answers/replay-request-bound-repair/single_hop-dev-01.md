# single_hop-dev-01

Using only the frozen documentation, at what boundary does a LangGraph checkpointer create full state snapshots, and why must a thread_id be supplied?

Component status: completed; error: None; new Provider calls: 1.

LangGraph 检查点在每个 **super-step 边界**创建完整状态快照：一个 super-step 是图的一次“tick”，该步调度的所有节点（可能并行）执行完毕；顺序图如 START -> A -> B -> END 会为输入、节点 A、节点 B 分别产生一个 super-step，从而各生成一个检查点[1]。节点（任务）级写入也会持久化，但那些只是任务条目，不是完整的 StateSnapshot；完整状态快照在 super-step 完成时提交[1]。必须提供 thread_id，是因为检查点以 thread_id 作为存储和检索检查点的主键；没有它，检查点无法保存状态，也无法在中断后恢复执行，因为检查点要靠 thread_id 加载已保存状态[1]。

Unresolved gaps: []
