# single_hop-dev-01 / workflow

Using only the frozen documentation, at what boundary does a LangGraph checkpointer create full state snapshots, and why must a thread_id be supplied?

Status: completed; answered: True; reason: None; model calls: 6; tools: 10; seconds: 25.127.

**结论**：LangGraph 在每个 **super-step 边界**创建 checkpoint；完整状态快照在该 super-step 完成后才提交。调用带 checkpointer 的图时，必须在 `config` 的 `configurable` 部分提供 `thread_id`，因为 checkpointer 以它作为存储和检索 checkpoint 的主键，没有它就无法保存状态或在 interrupt 后恢复执行 [1]。

**快照创建边界**

- super-step 是图的一次“tick”，该步调度的所有节点在此执行（可并行）。对 `START -> A -> B -> END` 这类顺序图，输入、节点 A、节点 B 各占一个 super-step，每步之后产生一个 checkpoint [1]。
- 节点（task）级写入会先记录到 `checkpoint_writes`，与进行中的 checkpoint 关联；同一 super-step 内其他节点失败时，已完成节点的写入已持久化，恢复时无需重跑。**完整状态快照在 super-step 完成后提交** [1]。
- 因此可恢复的边界是 super-step 边界，这也正是 time travel 只能从 checkpoint 恢复执行的原因 [1]。

**为什么必须提供 thread_id**

- thread 是分配给每个 checkpoint 的唯一标识，承载一串 run 的累积状态；执行 run 时图状态被持久化到该 thread [1]。
- checkpointer 用 `thread_id` 作为存储与检索 checkpoint 的主键；缺少它，checkpointer 无法保存状态，也无法在 interrupt 后加载已保存状态恢复执行 [1]。
- 持久化前必须先创建 thread [1]。

**取舍与适用条件**

- 默认每个 super-step 写入所有状态通道的完整值，长线程（如多轮对话）会显著增长存储；`DeltaChannel` 只存增量以减小 checkpoint 体积，代价是存储与延迟的权衡 [1]。
- 上述边界与主键要求适用于使用 checkpointer 的图；Agent Server 场景由服务端自动处理持久化，无需手动配置 [2]。

**材料缺口**：本次可见材料未给出 `checkpoint_writes` 的具体表结构字段或失败重试的完整语义，无法据此确认更细的重执行边界。

## Sources

1. Checkpointers — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/checkpointers.mdx
2. Persistence — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/persistence.mdx
