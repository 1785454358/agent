# conflicting_evidence-dev-02 / workflow

Using only the frozen documentation, reconcile super-step checkpoint boundaries with durable per-task writes that avoid rerunning successful sibling nodes after a failure.

Status: completed; answered: True; reason: None; model calls: 6; tools: 14; seconds: 29.935.

**结论：两者不是同一层级的持久化，而是“边界快照 + 任务级写入”互补。** super-step 边界提交完整 `StateSnapshot` 检查点，供时间旅行与从完整步骤恢复；同一 super-step 内每个节点完成时，其输出作为任务条目写入 `checkpoint_writes`，链接到进行中的检查点。若同一步中另一节点失败，成功兄弟节点的写入已持久化，恢复时不会重跑它们 [1]。

**机制与顺序**

1. 一个 super-step 是图中所有被调度节点执行的一个“tick”，可并行；LangGraph 在每个 super-step 边界创建检查点，时间旅行只能从这些完整检查点恢复 [1]。
2. 节点级写入通过 `put_writes`/`aput_writes` 保存单个任务的输出行，按 `(thread_id, checkpoint_ns, checkpoint_id)` 链接到检查点 [1]。
3. 完整状态快照在 super-step 完成后才提交；任务写入在此之前已落盘，因此失败恢复可复用成功节点的结果 [1]。

**取舍与边界**

- 任务写入不是完整 `StateSnapshot`，不能作为时间旅行起点；时间旅行仍须从 super-step 边界的完整检查点恢复 [1]。
- 该机制只保证“同一 super-step 内已成功节点不重跑”，不保证失败节点自身不重跑，也不改变重试策略与错误处理器的行为 [1][2]。
- 持久性取决于所用 checkpointer：`MemorySaver`/`InMemorySaver` 存于内存，进程重启即丢失，生产应使用持久化 checkpointer [3]。

**无法从当前材料确认**：`checkpoint_writes` 的具体保留/清理策略、跨 super-step 的写入合并细节，以及不同 durability 模式对任务写入时机的精确影响；这些需查阅对应配置与存储实现文档，不能由上述结论外推。

## Sources

1. Checkpointers — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/checkpointers.mdx
2. Fault tolerance — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/fault-tolerance.mdx
3. Persistence — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/persistence.mdx
