## 结论

Checkpoint 与 Store 是两套互补的持久化系统：**checkpointer 保存“某个线程的图状态快照”，按 thread_id 隔离，用于会话连续性、human-in-the-loop、time travel 与容错；Store 保存“应用自定义的键值数据”，按命名空间跨线程共享，用于用户偏好、事实与共享知识** [1]。多数应用两者并用：checkpointer 跟踪当前线程，store 跟踪跨线程的持久信息 [1]。

关键取舍：需要“从断点继续执行/恢复 interrupt”时用 checkpointer；需要“换一个会话仍能读到同一份数据”时用 Store。二者可同时配置：`builder.compile(checkpointer=checkpointer, store=store)` [1]。

## 对比表

| 维度 | Checkpointer | Store |
|---|---|---|
| 持久化内容 | 图状态快照（channel 值、待执行写入等）[2][1] | 应用定义的键值/JSON 文档数据 [3][4][1] |
| 作用域 | 单个线程 [1] | 跨线程 [3][1] |
| 记忆类型 | 短期、线程范围记忆 [4][1] | 长期、跨线程记忆 [4][1] |
| 典型用途 | 会话连续性、human-in-the-loop、time travel、容错 [1] | 用户偏好、事实、共享知识 [1] |
| 访问方式 | 在图 config 中传 `thread_id` [2][1] | 在节点或应用代码中读写条目 [1] |
| 组织机制 | thread_id（必填）+ 可选 checkpoint_id [2] | 自定义命名空间（类似文件夹）+ 唯一键（类似文件名）[4] |
| 配置前提 | `compile(checkpointer=...)`，调用时提供 thread_id [2][1] | 传入 store 实例，按命名空间组织 [3][4][1] |

## 进程重启

- **事实**：MemorySaver/InMemorySaver 把 checkpoint 存在内存中，进程重启后所有 checkpoint 丢失；生产应改用持久化 checkpointer，如 PostgresSaver、SqliteSaver [1]。
- **事实**：thread_id 是持久化游标，复用同一 thread_id 会恢复同一 checkpoint，新值则开启空状态的新线程 [5]。
- **推断**：因此“新进程 + 持久化后端 + 相同 thread_id + 相同图配置”是恢复图状态的前提；内存后端下无法跨重启恢复。
- **无法确认**：本次材料未逐项说明各持久化后端（Postgres/Sqlite 等）在重启后的具体保留语义差异，也未明确 Store 各后端重启后的保留行为；仅能确认 Store 是“持久化键值存储”抽象，具体保留取决于实现 [3]。

## interrupt 恢复

- **事实**：使用 interrupt 必须启用 checkpointer，该特性依赖持久化图状态 [6]。checkpointer 写入精确图状态以便稍后恢复，即使处于错误状态 [5]。
- **事实**：恢复时用相同 config（含 thread_id）调用 `graph.stream`/`invoke` 并传入 `Command(resume=...)`，恢复值成为节点内 `interrupt()` 的返回值 [5][6]。
- **事实**：图从节点开头恢复，**重新执行**该节点全部逻辑；一个节点内多个 interrupt 按顺序匹配恢复值 [6]。
- **前提**：checkpointer 已配置、thread_id 与中断时一致、恢复输入通过 Command 传入 [5][6]。

## 跨线程共享

- **事实**：checkpoint 按线程隔离，保存对话历史等状态，使不同线程保持分离的同时可访问该会话完整上下文 [4]。
- **事实**：Store 支持跨线程共享，可按用户 ID、助手 ID 或其他任意命名空间划分范围 [3]；长期记忆以 JSON 文档存于 store，命名空间常含用户或组织 ID，支持层级组织与跨命名空间的内容过滤搜索 [4]。
- **前提**：共享依赖命名空间/键的组织约定，而非 thread_id [3][4]。
- **事实**：子图更新状态时父图可能不立即看到，因各子图管理自己的 checkpoint 命名空间；需要跨图边界的数据应通过 Store 共享 [1]。

## 适用场景

- **Checkpoint**：多轮对话连续性、人工审批/中断恢复、回放与 time travel、故障后从断点续跑 [1]。
- **Store**：跨会话的用户偏好与事实、共享知识库、跨图/跨线程的指令或配置（如保存并更新 agent 指令提示词）[4][1]。
- **组合**：checkpointer 管当前线程状态，store 管跨线程长期数据 [1]。

## 来源

- [5] Interrupts: https://docs.langchain.com/oss/python/langgraph/interrupts
- [3] BaseStore: https://reference.langchain.com/python/langgraph/store/base/BaseStore
- [6] interrupt: https://reference.langchain.com/python/langgraph/types/interrupt
- [7] LangGraph overview: https://docs.langchain.com/oss/python/langgraph/overview
- [4] Memory overview: https://docs.langchain.com/oss/python/concepts/memory
- [2] langgraph.checkpoint: https://reference.langchain.com/python/langgraph/checkpoint
- [1] Persistence: https://docs.langchain.com/oss/python/langgraph/persistence
