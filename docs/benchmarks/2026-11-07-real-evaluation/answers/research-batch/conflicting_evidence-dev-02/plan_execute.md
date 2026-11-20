# conflicting_evidence-dev-02 / plan_execute

Using only the frozen documentation, reconcile super-step checkpoint boundaries with durable per-task writes that avoid rerunning successful sibling nodes after a failure.

Status: completed; answered flag: True; response reason: None; model calls: 6; seconds: 36.730.

**结论：** 冻结文档把两者设计为分层对齐而非冲突：完整检查点只在 super-step 边界提交，用于恢复与时间旅行；逐任务写入在 super-step 进行中即持久化，用于失败后跳过已成功的兄弟节点 [1]。

**边界定义**

- 检查点在每个 super-step 边界创建；super-step 是图中所有被调度节点执行（可能并行）的一次“tick”，顺序图 `START -> A -> B -> END` 在输入、A、B 各产生一个检查点，且只能从检查点（即 super-step 边界）恢复 [1]。
- 检查点是 `StateSnapshot` 形式的完整状态快照 [1]。

**逐任务写入**

- 除 super-step 检查点外，LangGraph 在节点（任务）级别持久化：每个节点在 super-step 内完成时，其输出作为任务条目写入 `checkpoint_writes` 表，并关联到进行中的检查点；完整快照在 super-step 完成后才提交 [1]。
- 存储层上，`checkpoints` 表每个 super-step 一行，`writes` 表每个节点输出一行，按 `(thread_id, checkpoint_ns, checkpoint_id)` 关联 [1]。
- 写入接口为 `put_writes` / `aput_writes`，按任务存储当前 superstep 内的节点输出行 [1]。

**失败恢复语义**

- 若某 super-step 中一个或多个节点失败，可从最后成功步骤重启 [1]。
- LangGraph 保存该 super-step 中其他已成功完成节点的待定检查点写入；从该 super-step 恢复时不会重跑这些成功节点 [1]。
- 这些任务写入不是完整 `StateSnapshot` 检查点，因此时间旅行仍从 super-step 边界的完整检查点恢复 [1]。

**对齐与空白**

- 文档明确分工：逐任务写入在 super-step 进行中持久化，用于 pending writes 恢复；完整检查点仅在 super-step 完成时提交，用于时间旅行 [1]。未描述二者冲突。
- 文档未说明逐任务写入在节点完成瞬间与检查点提交之间的具体时序细节，也未给出跨存储后端的一致性保证 [1]。这些属于本次可见材料中的空白，不能据此推断全部文档无答案。

**适用条件：** 上述恢复语义以使用 checkpointer 为前提 [1]；未配置 checkpointer 时该机制不适用。

## Sources

1. Checkpointers — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/checkpointers.mdx
