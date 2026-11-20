# single_hop-dev-01 / plan_execute

Using only the frozen documentation, at what boundary does a LangGraph checkpointer create full state snapshots, and why must a thread_id be supplied?

Status: completed; answered flag: True; response reason: None; model calls: 6; seconds: 26.003.

**结论：** 冻结文档指出，checkpointer 在**每个 super-step 边界**创建完整状态快照；`thread_id` 是 checkpointer 存储和检索检查点的主键，缺少它就无法保存状态或在中断后恢复执行 [1]。

**快照边界**

- LangGraph 在**每个 super-step 边界**创建检查点；super-step 是图的一次“tick”，该步调度的所有节点（可能并行）执行 [1]。
- 以 `START -> A -> B -> END` 为例，输入、节点 A、节点 B 各有独立 super-step，每步之后产生一个检查点 [1]。
- 除 super-step 检查点外，节点（任务）级写入也会先持久化：同一 super-step 内每个节点完成时，其输出作为任务条目写入 `checkpoint_writes`，关联到进行中的检查点；**完整状态快照在该 super-step 完成后才提交** [1]。
- 适用条件：这是默认行为；文档另提到 `DeltaChannel` 可只存增量而非完整累积值，以降低追加型通道的检查点体积 [1]。

**为何必须提供 `thread_id`**

- thread 是分配给 checkpointer 保存的每个检查点的唯一 ID，包含一系列运行的累积状态 [1]。
- 调用带 checkpointer 的图时，**必须**在 config 的 `configurable` 部分指定 `thread_id`，例如 `{"configurable": {"thread_id": "1"}}` [1]。
- checkpointer 以 `thread_id` 作为存储和检索检查点的主键；没有它，checkpointer 无法保存状态，也无法在中断后恢复执行，因为恢复时需用 `thread_id` 加载已保存状态 [1]。

**取舍与边界**

- 按 super-step 提交完整快照，使时间旅行只能从检查点（即 super-step 边界）恢复 [1]；节点级写入则用于 pending writes 恢复：同一步中某节点失败时，已成功节点的写入已持久化，恢复时无需重跑 [1]。
- 完整快照的代价是长线程存储增长；文档建议对追加型通道使用 `DeltaChannel` 权衡存储与延迟 [1]。
- 以上仅依据本次可见的冻结文档；未涉及其他 checkpointer 实现的具体提交时序。

## Sources

1. Checkpointers — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/checkpointers.mdx
