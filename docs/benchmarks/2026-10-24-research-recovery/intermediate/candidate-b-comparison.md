## 结论

**Checkpoint 是“线程内的图状态快照”，Store 是“线程外的应用数据仓库”。** 前者以 `thread_id` 为主键，用于短期记忆、interrupt 恢复、时间旅行和容错；后者以 `namespace/key` 组织 JSON 文档，用于跨线程的长期记忆（用户偏好、事实、共享知识）[1][2][3]。两者需分别配置，不能互相替代：interrupt 恢复读的是 checkpoint，不是 Store [4]；跨线程共享应走 Store，不应依赖 checkpoint [2][3]。

## 表格比较

| 维度 | Checkpoint（checkpointer） | Store（BaseStore） |
|---|---|---|
| 官方用途 | 持久化线程的图状态，短期、线程范围记忆：对话连续性、HITL、时间旅行、容错 [3] | 持久化图状态之外的应用数据，长期、跨线程记忆：用户偏好、事实、共享知识 [3] |
| 存什么 | 每个 super-step 的图状态快照（`StateSnapshot`），含 channel 值、待执行写入等 [5] | 任意 JSON 文档，含 `namespace`、`key`、`value`、时间戳 [2] |
| 组织方式 | 以 `thread_id` 为主键存储和检索 [5] | 以 `namespace`（类似文件夹）+ `key`（类似文件名）组织，namespace 可为任意长度 [2] |
| 线程边界 | 线程隔离；无 `thread_id` 无法保存状态或中断后恢复 [5] | 与 thread 无关，可跨 thread 访问 [2] |
| 写入时机 | 每个 super-step 边界写一次 [5] | 由应用代码在节点中显式 `put` [2] |
| 检索能力 | 按 `thread_id`/`checkpoint_id` 取状态与历史 [5] | 按 namespace 列举、按 key 取，可配 embedding 做语义搜索 [2] |
| 典型场景 | 会话内短期记忆、HITL 审批、回放/时间旅行、故障续跑 [3] | 跨会话用户画像、共享知识库、跨图边界共享数据 [2][3] |

## 三种场景的行为与前提

**1. 进程重启**

- 事实：`MemorySaver`/`InMemorySaver` 把 checkpoint 存在 RAM，进程重启后全部丢失；生产应改用 `PostgresSaver`、`SqliteSaver` 等持久化后端 [3]。
- 事实：Store 的持久性取决于后端，官方列出 `PostgresStore`、`MongoDBStore`、`RedisStore`、`UpstashStore` 等实现 [2]；`InMemoryStore` 在内存中 [2]。
- 无法确认：文档未逐一明示每种 Store 后端重启后的保留行为，需按具体后端核查。
- 前提：checkpoint 恢复还需用同一 `thread_id` 重新调用 [5][4]。

**2. interrupt 恢复**

- 事实：`interrupt()` 暂停时保存当前图状态并等待恢复输入；恢复需三项前提——checkpointer（生产用持久化后端）、config 中的 `thread_id`、可 JSON 序列化的 payload [4]。
- 事实：恢复时从 checkpoint 加载状态，而非从 Store 读取 [4]。
- 事实：恢复会从节点开头重跑，`interrupt` 之前的代码会再次执行；多个 interrupt 按索引匹配 resume 值 [4]。
- 事实：前端刷新后 interrupt 仍可见，依赖线程的 checkpoint [6]。
- 推断：若只用 Store 不配 checkpointer，interrupt 无法按原状态恢复——这是由“恢复读 checkpoint”直接推出的，文档未用反例明说。

**3. 跨线程共享**

- 事实：Store 通过 `namespace`/`key` 跨 thread 访问，namespace 常含 user/org ID；支持跨 namespace 的内容过滤检索 [1][2]。
- 事实：checkpoint 以 `thread_id` 隔离，用于线程内短期记忆 [1][5]。
- 事实：子图更新状态时父图可能看不到，因各自管理 checkpoint namespace；官方建议跨图边界的数据用 Store 共享 [3]。
- 推断：把 checkpoint 当跨线程共享通道不符合其设计边界，官方未提供按任意 namespace 跨线程读 checkpoint 的用法。

## 适用场景与取舍

- **会话内连续对话、审批中断、回放调试、失败续跑** → 用 checkpointer；代价是每个 super-step 全量写 channel 会带来存储增长，官方建议定期裁剪或设保留策略 [5][3]。
- **跨会话用户偏好、共享知识、跨子图共享** → 用 Store；代价是需自行设计 namespace 与写入逻辑，语义搜索还需配置 embedding [2]。
- **两者并用**：官方示例即同时编译 checkpointer 与 store，分别承担短期与长期记忆 [2][3]。

## 事实 / 推断 / 无法确认

- 事实：上述带 [n] 的表述均来自所列官方文档摘录。
- 推断：已标注“推断”的两条为逻辑推导，非原文直述。
- 无法确认：各 Store 后端重启保留行为的逐项差异；checkpoint 跨线程读取是否存在未列出的 API。

## 来源

- [1] Memory overview：https://docs.langchain.com/oss/python/concepts/memory
- [5] Checkpointers：https://docs.langchain.com/oss/python/langgraph/checkpointers
- [6] Human-in-the-Loop：https://docs.langchain.com/oss/python/langchain/frontend/human-in-the-loop
- [4] Interrupts：https://docs.langchain.com/oss/javascript/langgraph/interrupts
- [2] Stores：https://docs.langchain.com/oss/python/langgraph/stores
- [3] Persistence：https://docs.langchain.com/oss/python/langgraph/persistence
