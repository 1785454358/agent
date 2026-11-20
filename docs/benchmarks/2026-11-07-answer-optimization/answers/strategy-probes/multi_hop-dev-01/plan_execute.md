# multi_hop-dev-01 / plan_execute

Using only the frozen documentation, design memory for a user whose active conversation must resume after a pause and whose preferences must be available in a new thread. Which persistence mechanisms and identifiers belong where?

Status: completed; answered: True; reason: None; model calls: 6; seconds: 37.541.

**结论：两套机制分开归属。** 恢复暂停后的同一活跃对话用**检查点器（checkpointer）**，以 **`thread_id`** 定位；让偏好在新线程可用用**存储（store）**，以 **`user_id`** 作为记忆命名空间的一部分。多数应用同时使用两者：检查点器跟踪当前线程，存储跟踪跨线程的持久信息 [1]。

**恢复活跃对话：检查点器 + `thread_id`**

- 检查点器把线程的图状态持久化为检查点，用于短期、线程范围的记忆，包括对话连续性、人在回路、时间旅行和容错 [1]。
- `thread_id` 是检查点器存储和检索检查点的主键；没有它，检查点器无法保存状态或在中断后恢复执行，因为它用 `thread_id` 加载已保存状态 [2]。调用带检查点器的图时，必须在 `configurable` 中指定 `thread_id` [2]。
- 因此暂停后恢复同一对话，应复用同一 `thread_id` 重新调用图；换新 `thread_id` 即视为另一线程。

**跨线程偏好：存储 + `user_id`**

- 存储持久化应用定义的键值数据，范围跨线程，属长期跨线程记忆，用于用户偏好、事实和共享知识 [1]。
- 记忆以元组命名空间，示例为 `(user_id, "memories")`；`user_id` 作为该用户记忆的命名空间，可从 Runtime 上下文获取，与线程的 `thread_id` 不同 [3]。
- 示例中同一 `user_id` 在不同线程（`thread_id` "1" 与 "2"）下复用，以在新线程中访问该用户的记忆 [3]。

**归属对照**

| 场景 | 机制 | 标识符 | 作用域 | 访问方式 |
|---|---|---|---|---|
| 暂停后恢复活跃对话 | 检查点器 | `thread_id` | 单线程 | 图配置中传 `thread_id` [1][2] |
| 新线程中可用偏好 | 存储 | `user_id`（命名空间） | 跨线程 | 节点或应用代码读写 [1][3] |

**取舍与条件**：两者互补而非替代——检查点器保存的是图状态快照，存储保存的是应用定义的键值数据 [1]；偏好不应塞进线程状态，否则新线程不可见；对话历史也不应只放存储，否则无法按线程恢复执行。注意 `MemorySaver`/`InMemorySaver` 把检查点存于内存，进程重启即丢失，生产需换持久化检查点器 [1]；`PostgresSaver` 下 `thread_id` 需控制在 255 字符以内 [1]。

**缺口说明**：以上仅依据本次可见的冻结文档片段；文档未展示的存储后端细节与部署配置不在本回答范围内，无法据此确认。

## Sources

1. Persistence — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/persistence.mdx
2. Checkpointers — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/checkpointers.mdx
3. Stores — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/stores.mdx
