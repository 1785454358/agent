# single_hop-dev-01 / multi_agent

Using only the frozen documentation, at what boundary does a LangGraph checkpointer create full state snapshots, and why must a thread_id be supplied?

Status: completed; answered flag: True; response reason: None; model calls: 5; seconds: 27.015.

**结论**：完整状态快照在 **super-step 边界**创建；`thread_id` 是 checkpointer 存储与检索 checkpoint 的主键，缺失则无法保存状态、也无法在 interrupt 后恢复。

**快照边界**

LangGraph 在每个 super-step 边界创建一个 checkpoint。super-step 是图的一次“tick”，该步调度的所有节点（可能并行）执行；对 `START -> A -> B -> END` 这样的顺序图，输入、节点 A、节点 B 各有独立 super-step，因此每步之后各产生一个 checkpoint [1]。

需要注意粒度区别：除 super-step checkpoint 外，LangGraph 还在节点（任务）级持久化写入——super-step 内每个节点完成时，其输出作为任务条目写入 `checkpoint_writes` 表并关联进行中的 checkpoint，用于 pending writes 恢复；**完整状态快照在 super-step 完成后才提交** [1]。

默认情况下，每个 super-step 写入每个状态通道的完整值；对状态累积较大的长期线程（如多轮对话），这会造成存储显著增长 [1]。

**为何必须提供 thread_id**

使用 checkpointer 调用图时，**必须**在 config 的 `configurable` 部分指定 `thread_id` [1]。checkpointer 以 `thread_id` 作为存储和检索 checkpoint 的主键；没有它，checkpointer 无法保存状态，也无法在 interrupt 后恢复执行，因为其依赖 `thread_id` 加载已保存状态 [1]。

从作用范围看，checkpointer 持久化的是单个线程范围内的图状态快照，访问方式即在图 config 中传入 `thread_id`；store 则跨线程持久化应用定义数据 [2]。

**适用条件**：以上为冻结文档的表述；具体存储后端（如 PostgresSaver）对 `thread_id` 长度另有约束（建议小于 255 字符）[2]，属于实现层限制，不改变上述主键语义。

## Sources

1. Checkpointers — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/checkpointers.mdx
2. Persistence — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/persistence.mdx
