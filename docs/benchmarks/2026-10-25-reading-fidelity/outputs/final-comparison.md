## 结论

**checkpoint 是“线程内的图状态快照”，Store 是“跨线程的应用数据仓库”。** 前者按 `thread_id` 隔离，用于对话连续性、human-in-the-loop（HITL）、time travel 和容错；后者按自定义 namespace 组织任意键值数据，可从任意线程访问，用于用户偏好、事实和共享知识。多数应用两者并用：checkpointer 跟踪当前线程，store 跟踪跨线程的持久信息 [1]。

**关键取舍**：需要“从断点原样恢复执行”时，必须依赖 checkpointer（且需持久化后端）；需要“换一个线程仍记得用户”时，用 Store。Store 不承担 interrupt 断点恢复职责——官方 interrupt 恢复说明只涉及 checkpointer 与 `thread_id` [2][1]。

## 表格比较

| 维度 | Checkpointer（checkpoint） | Store |
|---|---|---|
| 保存内容 | 线程的图状态快照：channel 值、channel 版本、按节点的版本跟踪、待处理写入 [3]；通常含对话历史、上传文件、检索文档、生成产物 [4] | 图状态之外的应用自定义任意键值数据（JSON 文档），按 namespace + key 组织 [5][1] |
| 作用域 | 线程范围（短期记忆），按 `thread_id` 隔离 [4][1] | 自定义 namespace（字符串元组），不限于单个 thread ID [4][5] |
| 访问方式 | 在 graph config 中传 `thread_id` [1] | 在节点或应用代码中读写（`store.put` / `store.search`）[5][1] |
| 典型用途 | 对话连续性、HITL、time travel、容错 [1] | 用户偏好、积累知识、跨会话事实、共享知识 [5][1] |
| 进程重启 | 内存 saver 全部丢失；Postgres/Sqlite 等持久化后端可保留 [1] | 取决于后端实现；`InMemoryStore` 为内存实现 [5] |
| interrupt 恢复 | 必需：保存精确图状态，用同一 `thread_id` 恢复 [2] | 不参与断点恢复，仅提供长期记忆 [1] |
| 跨线程共享 | 按线程隔离，官方未提供常规跨线程读取方式 [4][1] | 支持，同一 Store 实例 + namespace 约定即可跨线程访问 [5] |

## 分场景说明

### 1. 进程重启

- **事实**：`MemorySaver`/`InMemorySaver` 把 checkpoint 存在内存，进程重启后全部丢失；生产应改用 `PostgresSaver`（PostgreSQL，支持异步）或 `SqliteSaver`（本地文件，用于开发）[1]。`PostgresSaver` 需调用 `setup()` 建表 [3][1]。
- **事实**：saver 选型上，`InMemorySaver` 仅用于调试测试，`SqliteSaver` 用于轻量演示，`AsyncSqliteSaver` 不推荐生产，`PostgresSaver`/`AsyncPostgresSaver` 用于带完整 checkpoint 历史的生产负载 [3]。
- **事实**：Store 侧，`InMemoryStore` 是最简单的参考实现，也可继承 `BaseStore` 接其他存储后端 [5]。
- **无法确认**：本次可见材料未明示 Store 各持久化后端在进程重启后的具体保留行为与配置前提；不能据 `InMemoryStore` 推断所有 Store 实现的重启语义。

### 2. interrupt 恢复

- **事实**：`interrupt` 在节点内暂停执行，LangGraph 保存当前图状态并等待输入；使用前提是配置 checkpointer（生产用持久化 checkpointer）[2]。
- **事实**：`thread_id` 是持久游标——复用同一值恢复同一 checkpoint，用新值则开启空状态的新线程 [2]。恢复时用同一 config（含相同 `thread_id`）调用 `graph.invoke(Command(resume=...))`，resume 值成为节点内 `interrupt()` 的返回值 [2]。
- **事实**：恢复会从节点开头重新执行，而非从 `interrupt` 调用行继续；节点内多个 interrupt 按索引顺序匹配 resume 值 [6]。
- **事实**：Store 的定位是长期、跨线程记忆，官方 interrupt 恢复说明只涉及 checkpointer 与 `thread_id` [2][1]。
- **推断**：因此 Store 在 interrupt 恢复中不承担状态回放角色；若节点逻辑需要长期记忆，可在恢复后的节点内自行读 Store，但这不是恢复机制的一部分。

### 3. 跨线程共享

- **事实**：checkpoint 按 `thread_id` 隔离，保持不同线程之间的分离 [4]；子图各自管理自己的 checkpoint namespace，父图可能不会立即看到子图状态更新 [1]。
- **事实**：官方对跨图边界数据的建议是：用 Store 共享，或配置子图写入父 checkpoint [1]。
- **事实**：Store 保存可从任意线程访问的键值数据，作用域为自定义 namespace 而非单个 thread ID；新建线程后，只要 `user_id` 相同仍可访问同一批记忆 [5]。前提是使用同一 Store 实例/后端，并按 namespace 约定组织数据 [5]。
- **无法确认**：官方是否提供任何跨线程读取另一线程 checkpoint 的受支持接口——本次材料只说“未提供常规方式”，不能据此断言底层绝无可能。

## 适用场景

- **用 checkpointer**：多轮对话续接、需要人工审批后原样续跑、回放/分支历史、失败后从断点恢复 [1]。
- **用 Store**：跨会话记住用户偏好与事实、多线程共享知识、跨图边界传数据 [5][1]。
- **两者并用**：checkpointer 管“这一条线程走到哪”，Store 管“这个用户/组织长期是什么样” [1]。

## 来源

- [2] Interrupts（Python）：https://docs.langchain.com/oss/python/langgraph/interrupts
- [7] LangGraph overview：https://docs.langchain.com/oss/python/langgraph/overview
- [6] Interrupts（JavaScript）：https://docs.langchain.com/oss/javascript/langgraph/interrupts
- [4] Memory overview：https://docs.langchain.com/oss/python/concepts/memory
- [3] checkpoints 参考：https://reference.langchain.com/python/langgraph/checkpoints
- [5] Stores：https://docs.langchain.com/oss/python/langgraph/stores
- [1] Persistence：https://docs.langchain.com/oss/python/langgraph/persistence
