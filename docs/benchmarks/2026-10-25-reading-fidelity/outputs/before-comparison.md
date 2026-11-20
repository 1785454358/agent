## 结论

**checkpoint 是“线程内的执行状态快照”，Store 是“跨线程的长期记忆库”**。checkpoint 以 `thread_id` 为主键，保存每个 super-step 的图状态，用于恢复执行（含 interrupt 后恢复）；Store 以自定义 `namespace` + `key` 组织数据，不随图状态自动保存，需在节点内通过 `Runtime` 显式读写 [1][2][3]。

取舍：需要“断点续跑/人在回路”用 checkpointer；需要“跨会话记住用户偏好/事实”用 Store。二者可同时编译进图，但职责不重叠 [3]。

## 对比表

| 维度 | checkpoint（checkpointer） | Store |
|---|---|---|
| 用途 | 保存线程状态快照，支持恢复执行 [2] | 保存跨会话长期记忆 [1] |
| 数据组织 | Checkpoints 表（channel_values 等）+ Writes 表（节点输出）[2] | namespace（字符串元组）+ key + value 字典 [3] |
| 作用域 | 严格绑定单个 `thread_id`，线程间隔离 [1][2] | 自定义 namespace，跨线程共享 [1][3] |
| 与图状态关系 | 就是图状态本身 [2] | 不自动关联，需节点内显式 put/search [3] |
| 启用方式 | `compile(checkpointer=...)` 并在 config 传 `thread_id` [2] | `compile(store=...)`，节点参数注入 `Runtime` 访问 [3] |
| 持久化实现 | InMemorySaver（实验）、Sqlite/Postgres/Mongo 等 [2] | InMemoryStore、PostgresStore、MongoDBStore、RedisStore 等 [3] |

## 三种场景的行为与前提

**进程重启**
- 事实：使用持久化 checkpointer（如 `AsyncPostgresSaver`、`MongoDBSaver`）时，按同一 `thread_id` 可恢复图执行；`InMemorySaver` 仅用于实验/测试 [2][4]。
- 事实：Store 数据是否保留取决于后端；`InMemoryStore` 为内存实现 [3]。
- 推断：进程重启后能否恢复，取决于所选后端是否真正落盘，文档未逐一列出各后端重启语义。

**interrupt 恢复**
- 事实：需 checkpointer + config 中 `thread_id`；恢复必须用与中断时相同的 `thread_id`，`Command(resume=...)` 的值成为 `interrupt()` 返回值；节点会从头重跑 interrupt 之前的代码 [5]。
- 事实：`thread_id` 相当于持久游标，复用即恢复同一 checkpoint，新值则开新线程 [5]。
- 事实：Store 未被描述为参与 interrupt 恢复，仅作节点内读写辅助 [3][5]。

**跨线程共享**
- 事实：短期记忆线程隔离，长期记忆跨线程共享，存于自定义 namespace [1]。
- 前提：图需同时用 checkpointer 和 store 编译；节点内通过自动注入的 `Runtime` 显式调用 store，常以 `user_id` 作 namespace [3]。
- 无法确认：并发写入注意事项，本次可见材料未明确说明。

## 适用场景

- checkpoint：多轮对话续跑、HITL 审批中断恢复、错误状态回滚 [2][5]。
- Store：跨会话用户画像、偏好、事实记忆，按 namespace 组织检索 [1][3]。

## 来源

- [1] Memory overview: https://docs.langchain.com/oss/python/concepts/memory
- [2] Checkpointers: https://docs.langchain.com/oss/python/langgraph/checkpointers
- [4] Human-in-the-loop: https://docs.langchain.com/oss/python/langchain/human-in-the-loop
- [3] Stores: https://docs.langchain.com/oss/python/langgraph/stores
- [5] Interrupts: https://docs.langchain.com/oss/python/langgraph/interrupts

## 事实/推断/无法确认

- 事实：上述带 [n] 的表述均来自对应文档摘录。
- 推断：进程重启恢复能力依赖后端落盘，属合理推断，文档未逐后端展开。
- 无法确认：Store 并发写入的具体约束；各 Store 后端重启后的精确语义。建议查阅对应后端参考页核实。
