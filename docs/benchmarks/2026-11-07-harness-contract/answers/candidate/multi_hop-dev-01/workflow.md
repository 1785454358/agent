# multi_hop-dev-01 / workflow

Using only the frozen documentation, design memory for a user whose active conversation must resume after a pause and whose preferences must be available in a new thread. Which persistence mechanisms and identifiers belong where?

Status: completed; answered: True; reason: None; model calls: 6; tools: 14; seconds: 34.682.

**结论：两套持久化各放一处。** 活跃对话的恢复状态放 **checkpointer**，以 **thread_id** 为键；用户偏好放 **Store**，以 **user_id** 为命名空间。暂停后用同一 `thread_id` 调用图即可恢复；新线程换新 `thread_id`、沿用同一 `user_id` 即可读到偏好 [1][2][3]。

| 数据 | 机制 | 标识符 | 作用域 |
|---|---|---|---|
| 对话图状态快照 | Checkpointer | `thread_id`（config 的 `configurable` 中） | 单线程 [1][3] |
| 用户偏好等键值数据 | Store | `user_id`（命名空间，如 `(user_id, "memories")`） | 跨线程 [1][2] |

**条件与取舍**

- Checkpointer 保存完整图状态，用于对话连续性、human-in-the-loop、time travel 与容错；调用带 checkpointer 的图**必须**指定 `thread_id`，否则无法保存状态或在中断后恢复 [1][3]。
- Store 保存应用定义的键值数据，可从任意节点或应用代码读写，适合用户偏好、事实与共享知识 [1][2]。
- 两者互补，多数应用同时使用：checkpointer 跟踪当前线程，store 跟踪跨线程的持久信息 [1]。

**最小调用顺序**

```python
graph = builder.compile(checkpointer=checkpointer, store=store)
# 恢复暂停对话：同一 thread_id
config = {"configurable": {"thread_id": "1"}}
# 新线程：新 thread_id，同一 user_id
config = {"configurable": {"thread_id": "2"}}
# 节点内通过 Runtime 取 user_id 并写 store
namespace = (runtime.context.user_id, "memories")
await runtime.store.aput(namespace, memory_id, {"memory": memory})
```

节点内用 `Runtime` 访问 store 与 `user_id`；新线程只要 `user_id` 相同即可访问同一记忆 [2]。

**边界**

- `InMemorySaver`/`InMemoryStore` 存于内存，进程重启即丢失；生产应换持久化实现（如 `PostgresSaver`、`SqliteSaver`）[1]。
- `PostgresSaver` 的 `thread_id` 列有长度限制，建议控制在 255 字符内 [1]。
- 长对话 checkpoint 会累积，需定期清理或设保留策略 [1]。
- 使用 Agent Server 时持久化由服务端自动处理，无需手动配置 [1][3]。

以上均限于冻结文档所述；具体生产选型与容量指标文档未给出测量数据，需另行核查。

## Sources

1. Persistence — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/persistence.mdx
2. Stores — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/stores.mdx
3. Checkpointers — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/checkpointers.mdx
