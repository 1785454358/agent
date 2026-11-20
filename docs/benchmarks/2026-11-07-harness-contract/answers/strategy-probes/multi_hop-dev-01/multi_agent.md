# multi_hop-dev-01 / multi_agent

Using only the frozen documentation, design memory for a user whose active conversation must resume after a pause and whose preferences must be available in a new thread. Which persistence mechanisms and identifiers belong where?

Status: completed; answered: True; reason: None; model calls: 6; tools: 14; seconds: 33.908.

**结论：两套机制分工明确。** 活动对话的暂停与恢复用 **checkpointer**，以 **`thread_id`** 定位；跨线程的用户偏好用 **store**，以 **`user_id` 命名空间 + `memory_id`** 标识。二者可同时编译进同一图 [1][2]。

**归属对照**

| 需求 | 机制 | 标识/位置 | 依据 |
|---|---|---|---|
| 暂停后恢复活动对话 | Checkpointer（线程内图状态快照） | `config.configurable.thread_id`，为主键 | [1][3] |
| 新线程中可用偏好 | Store（跨线程键值数据） | 命名空间如 `(user_id, "memories")`；条目键 `memory_id` | [1][2] |

**条件与取舍**

- 恢复对话必须传 `thread_id`；没有它 checkpointer 无法保存状态或在中断后恢复 [3]。同一 `thread_id` 续接即恢复原对话 [1]。
- 偏好写入 store 的命名空间；新线程只要 `user_id` 相同仍可读到同一批记忆 [2]。命名空间可为任意长度、不必绑定用户，但本场景用 `user_id` 最直接 [2]。
- 写入时在节点中经 `Runtime` 取 `user_id`，用 `uuid` 生成 `memory_id`，调用 `runtime.store.aput(namespace, memory_id, ...)` [2]。

**最小调用顺序**

```python
graph = builder.compile(checkpointer=checkpointer, store=store)
config = {"configurable": {"thread_id": "1"}}
graph.stream(input, config, context=Context(user_id="1"))
```

先编译两者，再以 `thread_id` 定位线程、以 `context` 传 `user_id` 作为记忆命名空间 [1][2]。

**边界**：以上为冻结文档所述机制与调用方式；未涉及具体存储后端选型与容量指标，材料未给出，故不作断言。

## Sources

1. Persistence — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/persistence.mdx
2. Stores — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/stores.mdx
3. Checkpointers — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/checkpointers.mdx
