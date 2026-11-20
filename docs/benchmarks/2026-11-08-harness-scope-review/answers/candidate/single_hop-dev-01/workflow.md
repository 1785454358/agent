# single_hop-dev-01 / workflow

Using only the frozen documentation, at what boundary does a LangGraph checkpointer create full state snapshots, and why must a thread_id be supplied?

Status: completed; answered: True; reason: None; model calls: 7; tools: 12; seconds: 25.601.

**结论**：完整状态快照在 **super-step 边界**创建；`thread_id` 是 checkpointer 存取 checkpoint 的主键，缺了它就无法保存状态、也无法在 interrupt 后恢复 [1]。

**快照边界**

- LangGraph 在每个 super-step 边界创建一个 checkpoint；super-step 是图中该步调度的所有节点执行（可并行）的一个“tick”。顺序图 `START -> A -> B -> END` 会在输入、节点 A、节点 B 各产生一个 checkpoint [1]。
- 节点（任务）级写入也会持久化，但它们**不是**完整 `StateSnapshot` checkpoint；完整状态快照在 super-step 完成时提交，因此 time travel 只能从 super-step 边界的完整 checkpoint 恢复 [1]。
- 适用条件：上述边界描述针对带 checkpointer 的图执行；节点级写入用于同一 super-step 内其他节点失败时的 pending writes 恢复，不改变“完整快照按 super-step 提交”的边界 [1]。

**为何必须提供 `thread_id`**

- 调用带 checkpointer 的图时，**必须**在 config 的 `configurable` 部分指定 `thread_id`，例如 `{"configurable": {"thread_id": "1"}}` [1]。
- checkpointer 以 `thread_id` 作为存储和检索 checkpoint 的主键；没有它，checkpointer 无法保存状态，也无法在 interrupt 后恢复执行，因为需要用 `thread_id` 加载已保存状态 [1]。
- 补充条件：要持久化状态，线程须在执行前已创建 [1]；`PostgresSaver` 场景下 `thread_id` 还受列长度限制，建议保持在 255 字符以内 [2]。

**边界说明**：以上仅依据本次可见的冻结文档 [2][1]；未涉及其他 checkpointer 实现或未列出的 API 行为。

## Sources

1. Checkpointers — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/checkpointers.mdx
2. Persistence — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/persistence.mdx
