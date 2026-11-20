# multi_hop-dev-01 / workflow

Using only the frozen documentation, design memory for a user whose active conversation must resume after a pause and whose preferences must be available in a new thread. Which persistence mechanisms and identifiers belong where?

Status: completed; answered: True; reason: None; model calls: 6; tools: 28; seconds: 38.424.

**结论：** 用 checkpointer 保存活跃会话的图状态，恢复时以 `thread_id` 为主键；用 store 保存跨线程偏好，以 `(user_id, "memories")` 命名空间和 `memory_id` 条目键读写。两者互补，多数应用同时使用 [1]。

**会话恢复：checkpointer + thread_id**

checkpointer 在每个 super-step 保存图状态快照，按 thread 组织，用于会话连续性、human-in-the-loop、时间旅行和容错 [1][2]。恢复时它用 `thread_id` 加载已保存状态；`thread_id` 放在 config 的 `configurable` 部分，是存取 checkpoint 的主键，没有它无法保存状态或在 interrupt 后恢复执行 [2]。

标识符分工：`thread_id` 定位线程；`checkpoint_id` 定位具体快照，不指定时返回该 thread+namespace 的最新 checkpoint；`checkpoint_ns` 标识所属图或子图 [2]。

**跨线程偏好：store + user_id 命名空间**

store 持久化应用定义的键值数据，作用域跨线程，用于用户偏好、事实和共享知识；它不保存图状态快照，由节点或应用代码读写条目 [1]。命名空间是 tuple，示例为 `(user_id, "memories")`，可为任意长度、不必与用户绑定 [3]。`user_id` 经 Runtime context 注入节点，节点据此构造命名空间，并以 `memory_id`（如 uuid）作为条目键调用 `store.aput` 写入 [3]。检索用 `store.asearch(namespace, query=..., limit=...)` [3]。只要 `user_id` 相同，新线程仍可访问同一批记忆 [3]。

**划分与关联**

| 维度 | checkpointer | store |
|---|---|---|
| 保存内容 | 图状态快照 | 应用键值数据 |
| 作用域 | 单线程 | 跨线程 |
| 访问方式 | config 中传 `thread_id` | 节点或应用代码读写 |
| 标识符 | `thread_id`、`checkpoint_id`、`checkpoint_ns` | 命名空间 tuple、`user_id`、`memory_id` |

文档明确称两者互补：checkpointer 跟踪当前线程，store 跟踪跨线程持久信息 [1]。会话状态按 `thread_id` 隔离，偏好按 `user_id` 命名空间共享，二者无文档说明的自动关联，需应用代码分别读写。

**注意：** `thread_id` 在 PostgresSaver 下有长度限制，建议保持在 255 字符以内 [1]。

## Sources

1. Persistence — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/persistence.mdx
2. Checkpointers — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/checkpointers.mdx
3. Stores — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/stores.mdx
