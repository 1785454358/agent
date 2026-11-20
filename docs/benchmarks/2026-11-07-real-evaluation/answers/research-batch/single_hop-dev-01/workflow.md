# single_hop-dev-01 / workflow

Using only the frozen documentation, at what boundary does a LangGraph checkpointer create full state snapshots, and why must a thread_id be supplied?

Status: completed; answered flag: True; response reason: None; model calls: 6; seconds: 24.984.

**结论：** 完整状态快照在 **super-step 边界**创建；`thread_id` 是 checkpointer 存取检查点的主键，缺失则无法保存状态、也无法在中断后恢复。[1]

**快照边界**

LangGraph 在每个 super-step 边界创建检查点。super-step 是图的一次“tick”，该步调度的所有节点在其中执行（可并行）；顺序图 `START -> A -> B -> END` 会在输入、节点 A、节点 B 之后各产生一个检查点。[1]

节点级写入不等于完整快照：每个节点完成时，其输出作为任务条目写入 `checkpoint_writes` 表，关联到进行中的检查点；完整状态快照在 super-step 完成时才提交。因此时间旅行只能从 super-step 边界的完整检查点恢复。[1]

**为何必须提供 `thread_id`**

checkpointer 以 `thread_id` 作为存储和检索检查点的主键；没有它，checkpointer 无法保存状态，也无法在中断后恢复执行，因为它用 `thread_id` 加载已保存状态。[1] 使用 checkpointer 调用图时，必须在 config 的 `configurable` 部分指定 `thread_id`，例如 `{"configurable": {"thread_id": "1"}}`。[1]

**适用条件与边界**

上述“完整快照”指默认行为：默认在每个 super-step 为每个状态通道写入完整值；`DeltaChannel` 可改为只存增量，以降低存储增长，但这是另一配置下的取舍。[1] 另外，`thread_id` 过长会触发 `PostgresSaver` 的列长度错误，文档建议保持在 255 字符以内。[2]

## Sources

1. Checkpointers — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/checkpointers.mdx
2. Persistence — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/persistence.mdx
