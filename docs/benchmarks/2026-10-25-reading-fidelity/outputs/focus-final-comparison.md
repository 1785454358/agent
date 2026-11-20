## 结论

- **checkpoint（checkpointer）**：保存“某个 thread 的图状态”，以 `thread_id` 为主键，按线程隔离；用于短期记忆、故障恢复、interrupt 后继续执行和时间旅行 [1][2]。
- **Store**：保存“跨线程的长期记忆”，按自定义 namespace 组织键值/JSON 文档，与 thread 无关；用于跨会话、跨线程共享用户级或应用级数据 [2][3]。
- **取舍**：需要“接着上次这条对话跑”用 checkpointer；需要“换一条对话仍记得这个用户”用 Store。二者可同时配置，分工协作 [3]。

## 对比表

| 维度 | checkpoint / checkpointer | Store |
|---|---|---|
| 用途 | 持久化线程内图状态，支持恢复、interrupt、时间旅行 [1][2] | 保存跨线程长期记忆，任意线程召回 [2][3] |
| 存什么 | 每个 super-step 边界的完整 `StateSnapshot`；另有节点级 task 写入用于容错 [1] | namespace 下的键值/JSON 文档，可带索引做语义检索 [2] |
| 边界键 | `thread_id`（主键）[1] | 自定义 namespace（常含 user_id 等），非 thread ID [2][3] |
| 线程隔离/共享 | 状态按线程隔离，不同 thread 保持分离 [2] | 设计为跨线程共享；新建 thread 只要 user_id 相同仍可访问 [3] |
| 进程重启 | 持久化后端下可恢复线程状态；内存型不行 [1] | 取决于后端；文档示例用 `InMemoryStore` 并提示生产用 DB 后端 [2] |
| interrupt 恢复 | 依赖 checkpointer + 同一 `thread_id`，从 checkpoint 继续 [1] | 文档未说明其参与 interrupt 暂停/恢复 [1] |
| 访问方式 | 调用时 config 指定 `thread_id` [1] | compile 时传 `store`，节点经 `Runtime` 注入访问 `runtime.store` [3] |

## 分场景说明

**进程重启**

- 事实：checkpoint 会被持久化，可在之后恢复线程状态 [1]。
- 前提：使用持久化后端；`InMemorySaver` 是内存型，另有需独立安装的生产级实现 [1]。
- 边界：`durability="exit"` 只在执行退出时持久化，中间状态不保存，进程崩溃中途无法恢复 [1]。
- Store：文档示例明确 `InMemoryStore` 存内存字典、生产应换 DB 后端 [2]；但未逐一说明各后端重启后的保留行为——**无法确认**具体后端细节。

**interrupt 恢复**

- 事实：没有 `thread_id`，checkpointer 无法保存状态或在 interrupt 后恢复执行，因为它用 `thread_id` 加载已保存状态 [1]。
- 恢复从 super-step 边界的完整 checkpoint 继续；同一 super-step 中已成功节点的写入已持久化，无需重跑 [1]。
- Store 不参与该暂停/恢复机制（文档未说明其角色）[1]。

**跨线程共享**

- checkpoint：状态按线程隔离，文档未提供跨 thread 直接读取对方 checkpoint 状态的机制 [1][2]。
- Store：compile 时同时传 `checkpointer` 和 `store`，节点通过自动注入的 `Runtime` 访问 `runtime.store`（如 `aput`/`asearch`），按 `(user_id, "memories")` 等 namespace 组织；新建 thread 后 user_id 相同仍可访问同一批记忆 [3]。
- 前提：LangSmith 本地/托管环境下 base store 默认可用、无需 compile 时指定；启用语义搜索需在 `langgraph.json` 配置索引 [3]。

## 适用场景

- 多轮对话续接、人工审批中断后继续、失败重跑、回放历史状态 → checkpointer [1][2]。
- 用户偏好、跨会话事实、应用级配置等需跨对话复用 → Store [2][3]。
- 两者并用：线程内状态走 checkpoint，跨线程记忆走 Store [3]。

## 事实 / 推断 / 无法确认

- **事实**：以上带 [n] 的表述均来自所列官方文档摘录。
- **推断**：Store 后端重启保留能力“取决于后端”属合理推断，文档仅以 `InMemoryStore` 示例并建议生产用 DB 后端 [2]。
- **无法确认**：各具体 Store 后端（如 DB 型）重启后的精确保留语义、Store 是否参与 interrupt 流程，本次可见材料未说明。

## 来源

- [1] Checkpointers：https://docs.langchain.com/oss/python/langgraph/checkpointers
- [2] Memory overview：https://docs.langchain.com/oss/python/concepts/memory
- [3] Stores：https://docs.langchain.com/oss/python/langgraph/stores
