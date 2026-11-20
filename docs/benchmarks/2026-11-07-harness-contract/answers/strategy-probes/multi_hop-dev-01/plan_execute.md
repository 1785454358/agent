# multi_hop-dev-01 / plan_execute

Using only the frozen documentation, design memory for a user whose active conversation must resume after a pause and whose preferences must be available in a new thread. Which persistence mechanisms and identifiers belong where?

Status: completed; answered: True; reason: None; model calls: 8; tools: 12; seconds: 37.464.

**结论：两套持久化机制分工使用。** 活跃对话的暂停与恢复用 checkpointer，以 `thread_id` 标识线程；用户偏好用 store，以 `user_id` 作为命名空间，使其在新线程中仍可读取 [1][2][3]。

| 需求 | 机制 | 标识 | 作用域 |
|---|---|---|---|
| 暂停后恢复活跃对话 | Checkpointer（保存图状态快照） | `thread_id`，放在 graph config 的 `configurable` 中 | 单线程、短期 [1][3] |
| 新线程可用偏好 | Store（应用自定义键值数据） | `user_id` 命名空间，如 `(user_id, "memories")` | 跨线程、长期 [1][2] |

**条件与取舍**

- 恢复依赖 `thread_id`：checkpointer 以它为主键加载已保存状态；没有它就无法保存状态或在中断后恢复 [3]。因此暂停前必须把同一 `thread_id` 传回 config。
- 偏好不能依赖 `thread_id`：新线程的 `thread_id` 不同，但相同 `user_id` 仍能访问同一批记忆 [2]。所以偏好写入 store，按 `user_id` 命名空间组织。
- 两者可同时编译进图：`builder.compile(checkpointer=..., store=...)`，调用时 config 带 `thread_id`，节点内通过 runtime 的 `user_id` 读写 store [1][2]。
- 若用 `PostgresSaver`，`thread_id` 应保持在 255 字符以下，可用 UUID 或哈希生成确定性 ID [1]。
- `InMemorySaver`/`InMemoryStore` 仅存于内存，进程重启即丢失 [1]；需要跨重启持久化时应换用持久化后端，但具体后端选择需按部署条件另行确认。

**最小调用顺序**：编译时挂 checkpointer 与 store → 调用时 config 传 `thread_id` → 节点内以 `user_id` 为命名空间 `put`/`search` 偏好 [1][2]。

**边界**：以上仅说明机制与标识归属；store 的检索排序、索引配置等细节取决于具体后端，冻结文档未给出统一保证 [2]。

## Sources

1. Persistence — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/persistence.mdx
2. Stores — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/stores.mdx
3. Checkpointers — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/checkpointers.mdx
