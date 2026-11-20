# conflicting_evidence-dev-02 / workflow

Using only the frozen documentation, reconcile super-step checkpoint boundaries with durable per-task writes that avoid rerunning successful sibling nodes after a failure.

Status: completed; answered: True; reason: None; model calls: 6; seconds: 32.690.

**结论**：两者是同一套持久化机制的两个层次，不是冲突。super-step 边界是完整 `StateSnapshot` 检查点的提交点；per-task 写入是 super-step 内部节点完成时的增量持久化，先于完整快照落盘。失败恢复时，从该 super-step 的完整检查点出发，叠加已持久化的 pending writes，已成功的兄弟节点不重跑 [1]。

**边界与粒度**

- 检查点在每个 super-step 边界创建；super-step 是图的一次“tick”，该步调度的所有节点（可并行）执行。顺序图 `START -> A -> B -> END` 在输入、A、B 各产生一个检查点 [1]。
- 因此完整快照的粒度是“一个 super-step 完成后”，不是“每个节点完成后” [1]。

**per-task 写入**

- 除 super-step 检查点外，LangGraph 在节点（任务）级持久化：super-step 内每个节点完成时，其输出作为任务条目写入 checkpointer 的 `checkpoint_writes` 表，并关联到进行中的检查点 [1]。
- 完整状态快照在 super-step 完成后才提交 [1]。
- 存储位置是 checkpointer（thread 作用域），不是 Store；Store 存应用定义的跨 thread 键值数据 [2]。

**失败恢复如何避免重跑兄弟节点**

- 若同一 super-step 中某节点失败，其他已成功节点的写入已持久化；从该 super-step 恢复时不重跑成功节点 [1]。
- 恢复起点是该 super-step 的完整检查点，再叠加 pending writes；不是从任务写入单独恢复 [1]。
- 明确限制：任务写入不是完整 `StateSnapshot` 检查点，time travel 仍从 super-step 边界的完整检查点恢复 [1]。

**取舍**

- 要“不重跑成功兄弟节点”，依赖 per-task 写入的持久性；要“可 time travel / 从边界重放”，依赖 super-step 完整检查点。两者互补：前者细、后者全。
- 若只保留 super-step 快照而丢弃任务写入，则同一 super-step 内失败会丢失已完成节点的成果；若只保留任务写入，则无法从完整快照做 time travel [1]。

**缺口**：本次可见材料未给出 `checkpoint_writes` 的具体表结构、写入失败时的重试/回滚语义，也未说明不同 durability mode 下 per-task 写入的持久化保证差异；这些无法从现有原文确认。

## Sources

1. Checkpointers — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/checkpointers.mdx
2. Persistence — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/persistence.mdx
