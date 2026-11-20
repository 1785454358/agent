# conflicting_evidence-dev-02 / workflow

Using only the frozen documentation, reconcile super-step checkpoint boundaries with durable per-task writes that avoid rerunning successful sibling nodes after a failure.

Status: completed; answered: True; reason: None; model calls: 7; tools: 10; seconds: 31.668.

**结论：** 两者是“粗粒度快照 + 细粒度任务写入”的分层关系，而非替代关系。super-step 检查点只在每个 super-step 边界提交完整状态快照 [1]；同一 super-step 内每个节点完成时，其输出先作为任务条目写入 `checkpoint_writes` 并链接到进行中的检查点 [1]。因此同一步中某节点失败时，已成功兄弟节点的写入已持久化，恢复时无需重跑；完整快照则在该 super-step 完成后才提交 [1]。

**边界与写入的对应**

| 维度 | super-step 检查点 | per-task 写入 |
|---|---|---|
| 时机 | 每个 super-step 边界创建 [1] | 节点在 super-step 内完成时写入 [1] |
| 内容 | 状态通道值、下一步节点、config、metadata（source/writes/step）、时间、父检查点、任务列表 [1] | 单任务节点输出行，按 `(task_id, channel, value)` 组织 [1] |
| 链接 | 组织到 thread 中 [1] | 通过 `(thread_id, checkpoint_ns, checkpoint_id)` 链接到检查点 [1] |
| 用途 | 时间旅行只能从完整检查点恢复 [1] | 支持 pending writes 恢复 [1] |

**避免重跑兄弟节点的机制与条件**

机制：失败发生在同一 super-step 内、且该 super-step 尚未完成时，成功节点的任务写入已落盘；恢复从该进行中的检查点读取这些写入，跳过已成功节点 [1]。条件是该 super-step 的检查点与写入均已持久化，且恢复使用同一 thread 的检查点 [1]。

失败来源也会被检查点化：若节点失败后、处理器完成前图被中断或进程崩溃，恢复时处理器看到相同的 `NodeError` 上下文 [2]。

**取舍**

per-task 写入不是完整 `StateSnapshot`，不能作为时间旅行起点；时间旅行仍须从 super-step 边界的完整检查点恢复 [1]。因此该设计以“快照较粗、写入较细”换取失败恢复的粒度，代价是恢复逻辑需同时读取检查点与写入表。

**材料缺口**

本次可见材料未给出写入表在崩溃场景下的具体提交/刷盘顺序，也未给出恢复时跳过成功节点的具体调用序列；上述机制仅能按原文表述确认，不能补全实现细节。

## Sources

1. Checkpointers — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/checkpointers.mdx
2. Fault tolerance — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/fault-tolerance.mdx
