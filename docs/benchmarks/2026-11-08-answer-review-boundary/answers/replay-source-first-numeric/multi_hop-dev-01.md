# multi_hop-dev-01

Using only the frozen documentation, design memory for a user whose active conversation must resume after a pause and whose preferences must be available in a new thread. Which persistence mechanisms and identifiers belong where?

Component status: completed; error: None; new Provider calls: 1.

结论：把“暂停后恢复当前对话”的短期记忆放在 checkpointer，用 `thread_id` 标识该线程；把“新线程仍可用的用户偏好”放在 store，用 `user_id` 作为命名空间标识。两者互补，多数应用同时使用：checkpointer 跟踪当前线程，store 跟踪跨线程的持久信息[1]。

1) 当前对话的暂停与恢复：checkpointer 按线程保存图状态快照，用于短期、线程范围内的记忆，包括对话连续性、human-in-the-loop、时间旅行和容错[1]。调用带 checkpointer 的图时，必须在 config 的 `configurable` 部分指定 `thread_id`[2]。checkpointer 以 `thread_id` 作为存储和检索 checkpoint 的主键；没有它，checkpointer 无法保存状态，也无法在 interrupt 之后恢复执行，因为它用 `thread_id` 加载已保存状态[2]。因此恢复同一段对话时沿用同一 `thread_id`。

2) 新线程中的用户偏好：store 保存图状态之外的应用定义数据，用于长期、跨线程记忆，包括用户偏好、事实和共享知识[1]。store 中的记忆按 `tuple` 命名空间组织，示例为 `(<user_id>, "memories")`；命名空间可为任意长度、可表示任意内容，不必与用户绑定[3]。只要 `user_id` 相同，创建新线程后仍可访问同一批记忆[3]。因此偏好写入 store，并以 `user_id` 作为跨线程的稳定标识；新线程使用新的 `thread_id`，但保持同一 `user_id`。

3) 标识归属：`thread_id` 属于 checkpointer 的线程标识，放在图配置的 `configurable` 中[2]；`user_id` 用于 store 记忆命名空间，示例通过运行时上下文传入，并在节点中组成 `(user_id, "memories")` 命名空间[3]。二者不能互相替代：前者定位单线程状态，后者定位跨线程数据[1][3]。

4) 实现方式：编译图时可同时传入 checkpointer 与 store[1]；示例中 checkpointer 用 `InMemorySaver`、store 用 `InMemoryStore`，调用时配置 `thread_id`[1]。若使用 Agent Server，则无需手动实现或配置 checkpointers 或 stores，服务器在后台处理持久化基础设施[1]。

5) 一个与标识有关的限制：使用 `PostgresSaver` 或 `AsyncPostgresSaver` 时，`thread_id` 存储在长度有限的列中，超长会报数据库错误；应将 `thread_id` 保持在 255 字符以下，需要确定性 ID 时可用 UUID 或哈希[1]。

Unresolved gaps: []
