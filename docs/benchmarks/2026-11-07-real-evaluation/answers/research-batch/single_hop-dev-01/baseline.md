# single_hop-dev-01 / baseline

Using only the frozen documentation, at what boundary does a LangGraph checkpointer create full state snapshots, and why must a thread_id be supplied?

Status: completed; answered flag: True; response reason: None; model calls: 2; seconds: 11.089.

**结论：** 完整状态快照在**每个 super-step 边界**创建；`thread_id` 是 checkpointer 存取 checkpoint 的主键，缺了它就无法保存状态或从 interrupt 恢复。[1][2]

**快照边界**

- LangGraph 在每个 super-step 边界创建一个 checkpoint。super-step 是图的一次“tick”，该步调度的所有节点（可能并行）执行完毕。例如 `START -> A -> B -> END` 在输入、节点 A、节点 B 后各产生一个 checkpoint。[1]
- 节点（任务）级写入是另一层：super-step 内每个节点完成时，输出写入 `checkpoint_writes` 表，作为关联进行中 checkpoint 的任务条目；这些逐任务写入用于 pending writes 恢复。**完整状态快照要等该 super-step 完成后才提交**。[1]
- 因此可区分：节点级写入是增量/任务条目，完整快照的提交边界是 super-step 结束。时间旅行也只能从 checkpoint（即 super-step 边界）恢复。[1]
- 默认情况下，checkpointer 在每个 super-step 写入每个状态通道的完整值；`DeltaChannel` 则只存增量以减小 checkpoint 体积。[1]

**为什么必须提供 `thread_id`**

- 调用带 checkpointer 的图时，**必须**在 config 的 `configurable` 部分指定 `thread_id`。[1]
- checkpointer 以 `thread_id` 作为存储和检索 checkpoint 的主键；没有它，checkpointer 无法保存状态，也无法在 interrupt 后恢复执行，因为加载已保存状态依赖 `thread_id`。[1]
- 语义上，thread 是分配给每个 checkpoint 的唯一标识，包含一串 run 累积的状态；`thread_id` 相当于持久游标：复用同一值会恢复同一 checkpoint，用新值则开启空状态的新 thread。[1][2]

最小调用形式（文档示例）：`config = {"configurable": {"thread_id": "1"}}`，再传给 `invoke`/`stream`。[1][2][3]

## Sources

1. Checkpointers — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/checkpointers.mdx
2. Interrupts — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/interrupts.mdx
3. Streaming — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/streaming.mdx
