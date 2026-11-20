# multi_hop-dev-01 / multi_agent

Using only the frozen documentation, design memory for a user whose active conversation must resume after a pause and whose preferences must be available in a new thread. Which persistence mechanisms and identifiers belong where?

Status: completed; answered: True; reason: None; model calls: 6; seconds: 38.343.

**结论：** 会话恢复用 checkpointer，以 `thread_id` 定位；偏好跨线程可用用 store，以 `user_id` 作为命名空间。两者分别归属线程级与用户级，不能互换 [1][2][3]。

**会话恢复（线程级）**

- 机制：checkpointer 把图的线程状态保存为检查点快照，用于对话连续性、human-in-the-loop、时间旅行和容错 [1]。
- 标识符：`thread_id` 是 checkpointer 存取检查点的主键；不提供它就无法保存状态或在中断后恢复，因为 checkpointer 靠 `thread_id` 加载已保存状态 [3]。调用时在 `configurable` 中传入，如 `{"configurable": {"thread_id": "1"}}` [3]。
- 细化定位：`checkpoint_id` 可在 `thread_id` 之外定位某个具体快照，如 `get_state` 同时传两者；`get_tuple` 也按 `thread_id` 与 `checkpoint_id` 取检查点元组 [3]。
- 作用域：单个线程，属短期、线程级记忆 [1]。

**偏好跨线程（用户级）**

- 机制：store 在图的 state 之外保存应用定义的键值数据，用于用户偏好、事实和共享知识，属长期、跨线程记忆 [1][2]。
- 标识符：`user_id` 作为该用户记忆的命名空间；调用图时除 `thread_id` 外还传 `user_id`，节点可通过 `Runtime` 访问 store 与 `user_id` 来保存记忆 [2]。
- 可见性条件：新建线程（如 `thread_id` 为 `"2"`）时，只要 `user_id` 相同，仍可访问同一批记忆 [2]。

**归属与区分**

| 维度 | Checkpointer | Store |
| ---- | ---- | ---- |
| 持久化内容 | 图状态快照 | 应用定义的键值数据 |
| 作用域 | 单线程 | 跨线程 |
| 记忆类型 | 短期、线程级 | 长期、跨线程 |
| 标识符 | `thread_id`（可加 `checkpoint_id`） | `user_id` 命名空间 |
| 访问方式 | 图配置传 `thread_id` | 节点或应用代码读写 |

文档明确：checkpointer 跟踪当前线程，store 跟踪跨线程的持久信息，多数应用可同时使用 [1]。因此会话状态按线程隔离，偏好按用户跨线程共享 [1][2]。

**条件与取舍**

- 暂停后恢复必须复用同一 `thread_id`；换新 `thread_id` 即新线程，旧会话状态不会随之带入 [3]。
- 偏好要在新线程可见，必须复用同一 `user_id`；仅换 `thread_id` 不影响 store 读取 [2]。
- 示例中的 `InMemorySaver`/`InMemoryStore` 存于内存，进程重启即丢失；生产应改用持久化实现（如 `PostgresSaver`、`SqliteSaver`）[1]。
- 文档未给出两类存储在同一后端中的物理表结构细节；上述为机制与标识符层面的分配，具体部署需按所选实现核对。

## Sources

1. Persistence — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/persistence.mdx
2. Stores — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/stores.mdx
3. Checkpointers — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/checkpointers.mdx
