# multi_hop-dev-01

Using only the frozen documentation, design memory for a user whose active conversation must resume after a pause and whose preferences must be available in a new thread. Which persistence mechanisms and identifiers belong where?

Component status: completed; error: None; new Provider calls: 1.

按冻结文档，应同时使用 checkpointer 与 store：checkpointer 以 thread 为范围保存图状态快照，用于对话连续性、human-in-the-loop、time travel 与容错；store 保存图状态之外的应用自定义数据，用于跨 thread 的长期记忆，如用户偏好、事实与共享知识。多数应用两者并用：checkpointer 跟踪当前 thread，store 跟踪跨 thread 的持久信息[n][1]。

标识符归属：调用带 checkpointer 的图时，必须在 config 的 configurable 部分指定 thread_id；checkpointer 以 thread_id 为主键存取 checkpoint，没有它就无法保存状态或在 interrupt 后恢复执行[n][2]。store 的记忆按命名空间组织，示例为 (user_id, "memories")；命名空间可为任意长度、表示任意内容，不必与用户绑定[n][3]。新 thread 中只要 user_id 相同，仍可访问同一批记忆[n][3]。

因此：暂停后恢复活跃对话，依赖同一 thread_id 下的 checkpointer 状态；新 thread 中可用用户偏好，依赖以 user_id 为命名空间的 store 数据。若用 PostgresSaver 或 AsyncPostgresSaver，thread_id 应保持在 255 字符以内，可用 UUID 或哈希[n][1]。使用 Agent Server 时无需手动实现或配置 checkpointer 与 store，服务器在后台处理持久化基础设施[n][1]。

Unresolved gaps: []
