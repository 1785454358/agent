# multi_hop-dev-01 / workflow

Using only the frozen documentation, design memory for a user whose active conversation must resume after a pause and whose preferences must be available in a new thread. Which persistence mechanisms and identifiers belong where?

Status: completed; answered: True; reason: None; model calls: 7; tools: 24; seconds: 42.465.

**结论：两套机制分开存放。** 活跃会话的暂停/恢复用 **checkpointer**，以 `thread_id` 为主键；用户偏好用 **store**，以 `user_id` 命名空间加 `memory_id` 为键。两者可同时编译进同一图 [1][2]。

**1. 会话恢复：checkpointer + thread_id**

- Checkpointer 在每个 super-step 保存图状态快照，按 thread 组织，用于会话连续性、human-in-the-loop、time travel 与容错 [1][3]。
- 恢复暂停会话依赖它：没有 `thread_id` 就无法保存状态或在 interrupt 后恢复执行，因为加载已存状态靠 `thread_id` [3]。
- `thread_id` 必须放在 config 的 `configurable` 部分 [3]：

```python
config = {"configurable": {"thread_id": "thread-1"}}
```

- `checkpoint_id` 标识**同一 thread 内**的某个具体检查点；只给 `thread_id` 取最新快照，加 `checkpoint_id` 取指定快照 [3]。它用于回看/重放，不是恢复活跃会话的必需主键。
- 注意：`PostgresSaver` 的 `thread_id` 列长度有限，建议控制在 255 字符以内 [1]。

**2. 新线程可用偏好：store + user_id + memory_id**

- Store 保存图状态之外的应用自定义键值数据，用于跨线程长期记忆，如用户偏好、事实、共享知识 [1][2]。
- 记忆按元组命名空间组织，示例为 `(user_id, "memories")`；命名空间可为任意长度、表示任意含义，不必与用户绑定 [2]。
- 每条记忆是键值对：键为唯一 `memory_id`，值为记忆本身，用 `store.put` 写入 [2]。
- `user_id` 通过运行时上下文传入，节点内可用 `Runtime` 访问 store 与 `user_id`；换新 `thread_id` 但 `user_id` 相同，仍能读到同一批记忆 [2]。

```python
namespace = (user_id, "memories")
memory_id = str(uuid.uuid4())
store.put(namespace, memory_id, {"food_preference": "I like pizza"})
```

**3. 两类持久化的区分与放置**

| 维度 | Checkpointer | Store |
|---|---|---|
| 持久化内容 | 图状态快照 | 应用自定义键值数据 |
| 作用域 | 单个 thread | 跨 thread |
| 记忆类型 | 短期、线程级 | 长期、跨线程 |
| 访问方式 | config 中传 `thread_id` | 节点或应用代码读写 |
| 标识符 | `thread_id`（主键）、`checkpoint_id`（线程内定位） | `user_id`（命名空间）、`memory_id`（键） |

依据见 [1] 的对比表与 [2] 的命名空间说明。多数应用两者并用：checkpointer 跟踪当前线程，store 跟踪跨线程的持久信息 [1]。

**4. 设计落点**

- 会话状态：放 checkpointer，键为 `thread_id`；恢复时用同一 `thread_id` 重新 invoke。
- 用户偏好：放 store，命名空间 `(user_id, "memories")`，每条偏好一个 `memory_id`；新线程只需相同 `user_id`。
- 不要把偏好塞进图状态快照，否则它随 thread 隔离，新线程读不到；也不要用 `thread_id` 作为偏好命名空间，否则跨线程失效（此为对 [1][2] 作用域定义的设计推论，非原文示例）。

**缺口说明：** 本次可见材料未给出具体后端（如 Postgres/Redis）的选型对比、`checkpoint_ns` 的完整语义，以及 store 语义检索的配置细节（仅提及需在 `langgraph.json` 配置索引）[2]。这些无法从现有材料确认，需另行核查。

## Sources

1. Persistence — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/persistence.mdx
2. Stores — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/stores.mdx
3. Checkpointers — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/checkpointers.mdx
