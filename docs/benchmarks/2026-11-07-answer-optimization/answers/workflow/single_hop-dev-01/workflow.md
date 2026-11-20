# single_hop-dev-01 / workflow

Using only the frozen documentation, at what boundary does a LangGraph checkpointer create full state snapshots, and why must a thread_id be supplied?

Status: completed; answered: True; reason: None; model calls: 6; seconds: 23.840.

**结论：** 完整状态快照在**每个 super-step 边界**创建；`thread_id` 必须提供，因为它是 checkpointer 存取检查点的**主键**，缺失时无法保存状态，也无法在 interrupt 后恢复执行 [1]。

**快照边界**

- super-step 是图的一次“tick”，该步调度的所有节点（可并行）执行完毕 [1]。
- 顺序图 `START -> A -> B -> END` 在输入、节点 A、节点 B 各产生一个检查点 [1]。
- 节点级写入只是 `checkpoint_writes` 中的任务条目，用于同一 super-step 内其他节点失败时的恢复，**不是**完整 `StateSnapshot`；完整快照在 super-step 完成时提交 [1]。
- 因此 time travel 只能从 super-step 边界的完整检查点恢复 [1]。

**为何必须 `thread_id`**

- 检查点按 thread 组织，thread 是分配给每个检查点的唯一标识，承载一串 run 的累积状态 [1]。
- 调用带 checkpointer 的图时，必须在 config 的 `configurable` 中给出 `thread_id`，例如 `{"configurable": {"thread_id": "1"}}` [1]。
- 文档明确：checkpointer 以 `thread_id` 作为存储和检索检查点的主键；没有它就无法保存状态，也无法在 interrupt 后恢复，因为恢复依赖 `thread_id` 加载已保存状态 [1]。

**适用条件与边界**

- 上述粒度是默认行为；文档另提到 `DeltaChannel` 可只存增量以减小检查点体积，这是存储优化，不改变 super-step 提交边界 [1]。
- 本次可见材料未给出缺失 `thread_id` 时的具体报错文本，只说明功能上无法保存与恢复 [1]；该细节属当前材料缺口。

## Sources

1. Checkpointers — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/checkpointers.mdx
