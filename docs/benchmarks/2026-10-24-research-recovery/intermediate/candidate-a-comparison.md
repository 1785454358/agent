## 结论

Checkpoint 是**线程内**的图状态快照，以 `thread_id` 为主键，用于同一线程的续接、interrupt 恢复与时间旅行 [1][2]；Store 是**跨线程**的长期记忆存储，按自定义 `namespace`/`key` 组织 JSON 文档，可在任意线程召回 [3]。取舍：需要“恢复某次执行到哪一步”用 checkpoint；需要“记住用户偏好/事实并跨会话复用”用 Store。

## 表格比较

| 维度 | Checkpoint（checkpointer） | Store（长期记忆） |
|---|---|---|
| 用途 | 保存线程在某一时刻的图状态快照（`StateSnapshot`），每个 super-step 边界写一次 [1] | 保存跨会话、跨线程的用户/应用级数据 [3] |
| 保存内容 | Checkpoints 表存序列化图状态（`channel_values`、`channel_versions`、`versions_seen`）；Writes 表存节点输出/待处理写入 `(task_id, channel, value)` [1] | 以 JSON 文档存于自定义 `namespace`（类似文件夹）+ 独立 `key`（类似文件名）[3] |
| 线程边界 | 以 `thread_id` 为主键存储与检索；不指定则无法保存状态或 interrupt 后恢复 [1] | 作用域是自定义 namespace，而非单一 thread ID；跨线程共享 [3] |
| 恢复能力 | 同一 `thread_id` 可续接同一 checkpoint；新值则开新线程、空状态 [2] | 不负责“恢复执行位置”，只负责按 namespace/key 召回数据 [3] |
| 检索方式 | `get_tuple`/`list` 按配置（`thread_id`、`checkpoint_id`）取状态与历史 [1] | 按 namespace/key 读取；支持内容过滤与语义搜索 [3][4] |

## 三种场景

**进程重启**
- 事实：checkpoint 的持久性取决于所选 checkpointer 实现；`InMemorySaver` 仅用于实验，SQLite/Postgres/MongoDB 等为独立安装的持久化实现 [1]。文档提到异步写入模式下进程崩溃存在“可能未写入 checkpoint”的小风险，`"sync"` 模式在下一步前同步落盘以换取高持久性 [1]。
- 事实：Store 有 `InMemoryStore`（开发）与 `PostgresStore`（生产）等实现 [4]。
- 推断：因此“重启后是否保留”取决于是否使用数据库后端；用内存实现则重启丢失。文档未逐字给出“重启后内存实现必丢”的表述，此为由实现性质得出的推断。

**interrupt 恢复**
- 事实：使用 `interrupt` 需要三件事：checkpointer 持久化图状态（生产用持久化后端）、config 中的 thread ID、在目标位置调用 `interrupt()` [2]。
- 事实：恢复时复用同一 `thread_id` 即回到同一 checkpoint；新值则开新线程 [2]。恢复会**从节点开头重新执行**，而非从 `interrupt` 那一行继续，故 `interrupt` 前的代码会再跑一遍 [2]。
- 事实：Store 在此场景不承担恢复职责；文档未说明 Store 参与 interrupt 恢复。

**跨线程共享**
- 事实：短期记忆是 thread-scoped，长期记忆跨对话线程共享、可在任意线程任意时刻召回，作用域为自定义 namespace [3]。
- 事实：namespace 常含用户或组织 ID 等标签，支持层级组织与跨 namespace 的内容过滤搜索 [3]。
- 推断：checkpoint 按 `thread_id` 隔离，故跨线程共享应走 Store；这是由“以 thread_id 为主键”推出的结论，文档未用“隔离”一词直述。

## 适用场景

- Checkpoint：会话内消息历史与状态恢复、同一线程续接、interrupt 恢复、时间旅行（只能从 super-step 边界恢复）[3][1]。
- Store：跨会话/跨线程的用户偏好、事实、画像等长期记忆，支持语义搜索与按内容过滤 [3][4]。

## 事实 / 推断 / 无法确认

- 事实：上表与三场景中标注 [3]–[2] 的内容。
- 推断：内存后端重启即丢失；checkpoint“按线程隔离”的措辞。
- 无法确认（本次可见材料不足，不代表文档无答案）：Store 在进程重启后的具体保留条件、Store 与 interrupt 恢复的交互、各后端崩溃一致性的逐项保证。建议核查各 checkpointer/store 实现页与持久化指南。

## 来源

- [3] Memory overview：https://docs.langchain.com/oss/python/concepts/memory
- [1] Checkpointers：https://docs.langchain.com/oss/python/langgraph/checkpointers
- [4] Semantic Search for LangGraph Memory：https://www.langchain.com/blog/semantic-search-for-langgraph-memory
- [2] Interrupts：https://docs.langchain.com/oss/javascript/langgraph/interrupts
