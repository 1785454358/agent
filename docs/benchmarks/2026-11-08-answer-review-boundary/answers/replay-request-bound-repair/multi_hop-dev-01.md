# multi_hop-dev-01

Using only the frozen documentation, design memory for a user whose active conversation must resume after a pause and whose preferences must be available in a new thread. Which persistence mechanisms and identifiers belong where?

Component status: completed; error: None; new Provider calls: 1.

用两种互补机制：活跃对话的暂停后续跑用 checkpointer（短期、线程内记忆），按 thread_id 持久化图状态快照；用户偏好跨线程可用用 store（长期、跨线程记忆），按 user_id 命名空间保存。

- 活跃对话恢复：编译图时传入 checkpointer，调用时在 config 的 configurable 中必须指定 thread_id；checkpointer 以 thread_id 为主键存取检查点，没有它就无法保存状态或在中断后恢复执行[1][2]。
- 偏好跨新线程可用：编译图时同时传入 store；把偏好写入 store，命名空间用元组如 (user_id, "memories")，条目用 memory_id（如 uuid）标识[3]。只要 user_id 相同，新建 thread_id 的线程仍能访问同一批记忆[3]。
- 标识归属：thread_id 属于 checkpointer/图配置，标识单个对话线程；user_id 属于 store 命名空间，标识跨线程的用户记忆；memory_id 标识 store 中的单条记忆[2][3][1]。
- 两者可并用：checkpointer 跟踪当前线程，store 跟踪跨线程的持久信息[2]。
- 注意：PostgresSaver 的 thread_id 列长度有限，应保持在 255 字符以内，可用 UUID 或哈希[2]。

Unresolved gaps: []
