# multi_hop-dev-01 / plan_execute

Using only the frozen documentation, design memory for a user whose active conversation must resume after a pause and whose preferences must be available in a new thread. Which persistence mechanisms and identifiers belong where?

Status: partial; answered flag: False; response reason: answer_review_incomplete; model calls: 6; seconds: 48.737.

**结论：两套机制分工使用。** 活跃会话的暂停/恢复交给 checkpointer，以 `thread_id` 为主键；用户偏好交给 store，以 `user_id` 作 namespace、`memory_id` 作 key。两者可同时编译进同一图，但标识符不共享：恢复会话用 `thread_id`，新 thread 读偏好仍用同一 `user_id`。[1][2][3]

**会话恢复（checkpointer）**

- 保存内容：每个 super-step 边界保存一次图状态快照（`StateSnapshot`），即 checkpoint。[3]
- 主键与触发：`thread_id` 是存取 checkpoint 的主键；调用带 checkpointer 的图时必须在 `configurable` 中给出 `thread_id`，否则无法保存状态，也无法在 interrupt 后恢复。[3]
- 恢复方式：用同一 `thread_id` 再次调用图，checkpointer 按该 id 加载已保存状态；`get_tuple` 用配置中的 `thread_id` 与 `checkpoint_id` 取 checkpoint 元组，写入记录按 `(thread_id, checkpoint_ns, checkpoint_id)` 关联。[3]
- 边界：checkpoint 随长对话累积，会增加延迟与存储成本，应定期裁剪或设保留策略；生产环境应使用持久化 checkpointer（如 PostgresSaver、SqliteSaver），内存型在进程重启后全部丢失。[1]

**新线程偏好（store）**

- 保存内容：图状态之外的应用自定义键值数据，用于跨 thread 的长期记忆，如用户偏好、事实、共享知识。[1][2]
- 组织方式：`store.put` 需指定 namespace 与键值对；key 是记忆的唯一标识 `memory_id`，value 是记忆本身；文档示例以 `user_id` 作为该用户记忆的 namespace（如 `[userId, "memories"]`）。[2]
- 读取方式：节点通过 `Runtime` 访问 store 与 `user_id`；新建 thread 后只要 `user_id` 相同，仍可读到相同记忆（示例中 `thread_id` 由 "1" 改为 "2"，`user_id` 保持 "1"）。[2]

**归属对照**

| 维度 | checkpointer | store |
| ---- | ---- | ---- |
| 持久化对象 | 图状态快照 | 应用自定义键值数据 |
| 范围 | 单 thread | 跨 thread |
| 记忆类型 | 短期、thread 级 | 长期、跨 thread |
| 访问标识 | 图配置中的 `thread_id` | `user_id` namespace + `memory_id` key |
| 访问方式 | 图配置传入 | 节点或应用代码读写 |

依据：[1] 的对比表与“多数应用可同时使用”的说明；[2] 的 namespace/key 与跨 thread 示例；[3] 的 `thread_id` 主键与 `checkpoint_id` 定位规则。

**取舍与条件**

- 两者分离、不共享标识符：checkpointer 跟踪当前 thread，store 跟踪跨 thread 的持久信息；会话恢复只依赖 `thread_id`，偏好读取只依赖 `user_id`，因此新 thread 换 `thread_id` 不影响偏好可用。[1][2]
- `checkpoint_id` 用于定位具体 checkpoint（如回放、历史查询），不是恢复活跃会话的必需入口；无 `checkpoint_id` 时返回该 thread + namespace 的最新 checkpoint。[3]
- 若使用 Agent Server，文档称其自动处理持久化，无需手动配置 checkpointer 或 store；但语义搜索仍需在 `langgraph.json` 配置索引。[1][2]

**缺口说明**：本次可见材料未给出 store 的保留/清理策略，也未给出 `user_id` 的生成与鉴权规则；这些无法从现有文档确认，需另行核查。

## Sources

1. Persistence — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/persistence.mdx
2. Stores — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/stores.mdx
3. Checkpointers — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/checkpointers.mdx
