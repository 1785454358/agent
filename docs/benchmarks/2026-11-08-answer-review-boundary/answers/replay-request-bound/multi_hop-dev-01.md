# multi_hop-dev-01

Using only the frozen documentation, design memory for a user whose active conversation must resume after a pause and whose preferences must be available in a new thread. Which persistence mechanisms and identifiers belong where?

Component status: completed; error: None; new Provider calls: 1.

按冻结文档，应同时使用两种互补持久化机制：checkpointer 负责线程内短期记忆，store 负责跨线程长期记忆[1]。

1. 活动对话暂停后恢复：用 checkpointer。它按 thread 保存图状态快照，支持对话连续性、human-in-the-loop、时间旅行和容错[1]；调用图时必须在 config 的 configurable 中指定 thread_id，checkpointer 以 thread_id 为主键存取检查点，没有它就无法保存状态或在 interrupt 后恢复执行[2]。因此 thread_id 属于 checkpointer 的线程标识，放在图调用配置中[1][2]。

2. 新线程中仍可用用户偏好：用 store。它保存图状态之外的应用自定义数据，作用域跨线程，适合用户偏好、事实和共享知识[1]。记忆按命名空间组织，示例为 (user_id, "memories")；命名空间可为任意长度、可表示任意内容，不必与用户绑定[3]。新线程只要 user_id 相同，仍可访问同一批记忆[3]。因此 user_id 属于 store 的命名空间标识，通过运行时上下文传入，节点从 runtime.context 读取后以 (user_id, "memories") 命名空间读写记忆[3]。

3. 归属总结：thread_id 放 configurable 配置，供 checkpointer 定位当前线程状态；user_id 放运行时上下文，供 store 定位跨线程记忆命名空间。两者职责不同，不能互相替代[1][3][2]。

4. 实现方式：编译图时同时传入 checkpointer 和 store，例如 InMemorySaver 与 InMemoryStore，或 MemorySaver 与 MemoryStore[1]。生产环境可选 PostgresSaver、MongoDBSaver/MongoDBStore、RedisSaver 等，需单独安装[2]。若使用 Agent Server，则由服务器自动处理持久化，无需手动配置 checkpointer 或 store[1]。

5. 注意事项：使用 PostgresSaver 或 AsyncPostgresSaver 时，thread_id 存在长度受限的列中，应保持在 255 字符以内，可用 UUID 或哈希生成确定性 ID[1]。

Unresolved gaps: []
