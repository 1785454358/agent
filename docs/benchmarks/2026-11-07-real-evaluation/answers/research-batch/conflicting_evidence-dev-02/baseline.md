# conflicting_evidence-dev-02 / baseline

Using only the frozen documentation, reconcile super-step checkpoint boundaries with durable per-task writes that avoid rerunning successful sibling nodes after a failure.

Status: completed; answered flag: True; response reason: None; model calls: 2; seconds: 12.803.

**结论：两者不冲突，而是分层协作。** 超级步（super-step）边界上的完整检查点负责“可恢复的整图状态与时间旅行”；同一超级步内各节点（task）的持久写入负责“失败后不重跑已成功的兄弟节点”。恢复时从该超级步的检查点出发，已落盘的 task 写入被复用，只重跑失败或未完成的节点 [1]。

**机制与依据**

- 检查点按超级步边界创建，一个超级步内所有被调度的节点（可能并行）执行一次；完整状态快照在该超级步完成后才提交 [1]。
- 与此同时，每个节点完成时其输出即写入 `checkpoint_writes` 表，作为关联到进行中检查点的 task 条目；这些是 per-task 写入，不是完整 `StateSnapshot` [1]。
- 因此某节点在同一超级步中途失败时，其他已成功节点的写入已经持久化；从该超级步恢复时不会重跑这些成功节点 [1]。
- 存储层对应两张表：检查点表每超级步一行，写入表每节点输出一行，存 `(task_id, channel, value)` 并关联检查点 [1]。

**取舍与边界**

| 维度 | 超级步检查点 | per-task 写入 |
|---|---|---|
| 粒度 | 每超级步一个完整快照 | 每节点输出一条 |
| 用途 | 恢复、时间旅行、分叉 | 同超级步内失败恢复 |
| 时间旅行 | 只能从完整检查点恢复 [1] | 不能作为时间旅行起点 [1] |

- 时间旅行/重放仍以超级步检查点为起点；重放会重跑该检查点之后的节点，包括 LLM 调用、API 请求和中断 [1]。
- 若用 `DeltaChannel` 等增量通道，检查点 blob 只存哨兵，状态需通过重放祖先写入重建，读取成本与后端查询能力相关 [1]。
- 删除线程时检查点行与写入行都必须删除 [1]。

**实践含义**：把节点设计为可安全重入（副作用幂等或放在独立节点），因为失败恢复只保证不重跑已成功兄弟节点，不保证失败节点自身不重跑；中断恢复会重跑所在节点，副作用宜放在 `interrupt()` 之后 [2]。

## Sources

1. Checkpointers — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/checkpointers.mdx
2. Interrupts — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/interrupts.mdx
