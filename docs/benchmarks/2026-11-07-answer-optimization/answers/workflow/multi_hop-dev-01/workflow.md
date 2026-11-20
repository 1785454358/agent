# multi_hop-dev-01 / workflow

Using only the frozen documentation, design memory for a user whose active conversation must resume after a pause and whose preferences must be available in a new thread. Which persistence mechanisms and identifiers belong where?

Status: completed; answered: True; reason: None; model calls: 6; seconds: 35.104.

**结论：两套机制分开存放。暂停后恢复活跃对话用 checkpointer，以 `thread_id` 定位；新线程中可用的用户偏好用 store，以 `user_id` 命名空间定位。多数应用同时使用两者 [1]。**

| 场景 | 机制 | 标识符 | 归属与用法 |
|---|---|---|---|
| 暂停后恢复活跃对话 | checkpointer（检查点存储） | `thread_id`；可选 `checkpoint_id` | `thread_id` 是检查点存取主键，必须在 `config` 的 `configurable` 中传入，否则无法保存状态或在中断后恢复 [2]；`checkpoint_id` 只在给定 `thread_id` 下检索特定快照 [2] |
| 新线程可用偏好 | store（长期记忆） | `user_id`（命名空间元组如 `(user_id, "memories")`） | 从节点或应用代码读写 [1]；新线程只要 `user_id` 相同仍可访问同一记忆 [3] |

**条件与取舍**

- checkpointer 持久化图状态快照，作用域为单个线程，属短期线程记忆，用于对话连续性、human-in-the-loop、time travel 和容错 [1]。恢复同一对话必须复用原 `thread_id`；换新 `thread_id` 即新线程，不会加载原线程状态。
- store 持久化图状态之外的应用自定义键值数据，跨线程，属长期记忆，用于用户偏好、事实和共享知识 [1]。命名空间可为任意长度、不必与用户绑定，示例用 `(user_id, "memories")` [3]。
- 两者分离：`thread_id` 管当前线程，`user_id` 管跨线程持久信息；`user_id` 不是检查点主键，`thread_id` 也不用于偏好命名空间 [1][3][2]。

**最小调用顺序（Python 示例，原文形式）**

```python
graph = builder.compile(checkpointer=checkpointer, store=store)
config = {"configurable": {"thread_id": "1"}}
graph.invoke(inputs, config, context=Context(user_id="1"))
```

恢复时沿用同一 `thread_id`；开新线程时改 `thread_id`（如 `"2"`）但保持同一 `user_id`，即可在新线程读取偏好 [3]。

**边界**：以上仅据冻结文档；未涉及具体存储后端选型与并发/清理策略，文档未给出，故不展开。

## Sources

1. Persistence — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/persistence.mdx
2. Checkpointers — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/checkpointers.mdx
3. Stores — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/stores.mdx
