# conflicting_evidence-dev-02 / multi_agent

Using only the frozen documentation, reconcile super-step checkpoint boundaries with durable per-task writes that avoid rerunning successful sibling nodes after a failure.

Status: completed; answered flag: True; response reason: None; model calls: 6; seconds: 39.772.

**结论：** 冻结文档用“两层持久化”来调和这两个时点：super-step 边界提交完整检查点，供恢复与时间旅行使用；同一 super-step 内每个节点完成时，先把该任务输出写入 `checkpoint_writes` 并链接到进行中的检查点。因此，当同一 super-step 中另一节点失败时，已成功兄弟节点的写入已经持久化，恢复时无需重跑 [1]。

**边界定义**

- 检查点写在每个 super-step 边界，是图状态快照（`StateSnapshot`）；super-step 是该步所有被调度节点的一次执行，可能并行 [1]。
- 顺序图 `START -> A -> B -> END` 在输入、A、B 各产生一个检查点；只能从检查点（即 super-step 边界）恢复执行 [1]。

**任务级写入**

- 节点完成即写：每个节点在 super-step 内完成时，输出作为任务条目写入 `checkpoint_writes`，链接到进行中的检查点 [1]。
- 完整快照在 super-step 完成后才提交 [1]。
- 存储抽象上，检查点表每个 superstep 一行，存序列化图状态并链接父检查点；写入表每个节点输出一行，存 `(task_id, channel, value)` 并链接检查点；`put` 写检查点行，`put_writes` 写节点输出行 [1]。

**为何不重跑成功兄弟节点**

- 文档明确：同一 super-step 中另一节点失败时，成功节点的写入已持久化，恢复时无需重跑；这就是 pending writes 恢复机制 [1]。
- 这些任务写入不是完整 `StateSnapshot` 检查点，时间旅行仍从 super-step 边界的完整检查点恢复 [1]。

**冲突与限制**

- 时点差异：任务写入先于 super-step 完成提交，存在“部分任务已写入、完整检查点未提交”的中间态；文档正是用 pending writes 在该中间态恢复，而非要求整步重跑 [1]。
- 失败尝试的写入会被清除：节点超时触发 `NodeTimeoutError` 时，LangGraph 清除该失败尝试的写入，再由重试策略决定是否重试 [2]。因此“成功兄弟节点不重跑”依赖其写入未被清除且已持久化；失败节点自身的部分写入不保留。
- 恢复入口：从检查点恢复，任务级写入作为附属记录被读回（`get_tuple` 同时读取检查点与写入）[1]。

**适用条件**：上述行为以启用 checkpointer 为前提 [1]；未配置 checkpointer 时文档未给出任务级持久化保证。

## Sources

1. Checkpointers — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/checkpointers.mdx
2. Fault tolerance — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/fault-tolerance.mdx
