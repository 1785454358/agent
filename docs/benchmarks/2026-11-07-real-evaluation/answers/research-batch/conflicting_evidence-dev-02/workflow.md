# conflicting_evidence-dev-02 / workflow

Using only the frozen documentation, reconcile super-step checkpoint boundaries with durable per-task writes that avoid rerunning successful sibling nodes after a failure.

Status: completed; answered flag: True; response reason: None; model calls: 6; seconds: 35.280.

**结论：** 冻结文档把两层持久化分开：super-step 边界提交完整 `StateSnapshot` 检查点；同一 super-step 内每个节点完成时，先把输出作为任务条目写入 `checkpoint_writes` 表并链接到进行中的检查点。失败恢复正是靠这些已持久化的任务写入跳过已成功的兄弟节点，只重跑失败或未完成的任务 [1]。因此二者不是矛盾，而是“边界快照 + 边界内逐任务写入”的分工：快照用于时间旅行，任务写入用于容错恢复 [1]。

**边界定义**

- 检查点在每个 super-step 边界创建；super-step 是图中所有被调度节点执行（可能并行）的一个“tick”，同一 super-step 内的并行任务共享该边界 [1]。
- 检查点保存的是 super-step 完成时提交的完整图状态快照（`StateSnapshot`）[1]。

**每任务写入**

- 每个节点在 super-step 内完成时，其输出先作为任务条目写入 `checkpoint_writes` 表，链接到进行中的检查点；完整状态快照在 super-step 完成后才提交 [1]。
- 这些任务写入不是完整 `StateSnapshot` 检查点，所以时间旅行只能从 super-step 边界的完整检查点恢复 [1]。

**失败恢复语义**

- 若同一 super-step 中某节点失败，其他已成功完成节点的 pending writes 已被持久化；从该 super-step 恢复时不会重跑已成功的节点，只重跑失败或未完成的任务 [1]。
- 该跳过行为的条件：成功节点的写入已落盘到 `checkpoint_writes`，且恢复从该 super-step 的检查点开始 [1]。

**一致性与边界情形**

- 文档区分任务写入与完整检查点：任务写入用于容错恢复，完整检查点用于时间旅行 [1]。
- 超时或重试时会清除失败尝试的写入（clears any writes from the failed attempt），再决定是否重试 [2]。
- 文档未明确说明“部分任务已写入但检查点未提交”时的重复写入或幂等性要求；本次可见材料只支持上述清除失败尝试写入的处理 [2]，其余属未说明之处。

## Sources

1. Checkpointers — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/checkpointers.mdx
2. Fault tolerance — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/fault-tolerance.mdx
