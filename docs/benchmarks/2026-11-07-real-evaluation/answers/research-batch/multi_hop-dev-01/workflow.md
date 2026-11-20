# multi_hop-dev-01 / workflow

Using only the frozen documentation, design memory for a user whose active conversation must resume after a pause and whose preferences must be available in a new thread. Which persistence mechanisms and identifiers belong where?

Status: partial; answered flag: False; response reason: answer_review_incomplete; model calls: 6; seconds: 35.678.

**结论：** 会话恢复用 checkpointer，以 `thread_id` 定位；偏好跨线程复用用 Store，以 `user_id` 命名空间关联。两者可编译进同一图，但职责与标识符不同 [1][2][3]。

**会话恢复（线程级）**

- checkpointer 持久化图状态快照，作用域为单个线程，属短期、线程级记忆，用于对话连续性、human-in-the-loop、时间旅行与容错 [1]。
- 调用图时必须在 `configurable` 中传 `thread_id`；checkpointer 以它为主键存取检查点，没有它无法保存状态或在中断后恢复 [3]。
- 最小调用：`graph.invoke(input, {"configurable": {"thread_id": "thread-1"}})`，图需 `compile(checkpointer=checkpointer)` [1][3]。
- 限制：`PostgresSaver` 的 `thread_id` 列长度有限，应保持在 255 字符以下，可用 UUID 或哈希 [1]。`MemorySaver`/`InMemorySaver` 存于 RAM，重启不保留 [1]。

**偏好跨线程（用户级）**

- Store 持久化应用定义的键值数据，作用域跨线程，属长期记忆，用于用户偏好、事实与共享知识 [1]。
- 记忆按元组命名空间组织，示例为 `(user_id, "memories")`；命名空间可任意长度，不必须用户专属 [2]。
- 调用图时同时传 `thread_id` 与作为该用户命名空间的 `user_id`；新线程（如 `thread_id` 改为 `"2"`）只要 `user_id` 相同，仍可读取此前记忆 [2]。
- 节点内通过 `Runtime` 取 `user_id`，用 `store.put(namespace, memory_id, {...})` 写入，`memory_id` 可用 UUID [2]。

**归属对照**

| 维度 | checkpointer | Store |
| --- | --- | --- |
| 持久化内容 | 图状态快照 | 应用定义键值数据 |
| 作用域 | 单线程 | 跨线程 |
| 标识符 | `thread_id`（主键） | `user_id` 命名空间 |
| 用途 | 暂停后恢复、连续性 | 偏好、事实 |

**取舍与条件：** 恢复依赖同一 `thread_id` 且检查点存储可跨进程存活；偏好依赖同一 `user_id` 且 Store 持久化。二者不可互换：`thread_id` 不能承载跨线程偏好，`user_id` 也不能定位线程状态 [1][2][3]。若用 Agent Server，文档称其自动处理持久化，无需手动配置 [1]。

**缺口：** 本次可见材料未给出 Store 后端在重启后的持久化细节，也未给出暂停/恢复的具体中断 API 流程；上述设计仅基于已列文档。

## Sources

1. Persistence — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/persistence.mdx
2. Stores — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/stores.mdx
3. Checkpointers — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/checkpointers.mdx
