# multi_hop-dev-01 / multi_agent

Using only the frozen documentation, design memory for a user whose active conversation must resume after a pause and whose preferences must be available in a new thread. Which persistence mechanisms and identifiers belong where?

Status: completed; answered flag: True; response reason: None; model calls: 12; seconds: 83.696.

**结论：两套机制分工明确。** 活跃会话的暂停/恢复用 **checkpointer**，以 `thread_id` 为主键、`checkpoint_id` 定位具体检查点；跨线程偏好用 **store**，以 `user_id` 为命名空间、`memory_id` 为条目键。两者互补：checkpointer 跟踪当前线程，store 跟踪跨线程的持久信息 [1]。

**1. 会话恢复：checkpointer + thread_id**

- checkpointer 以检查点保存线程的图状态，用于短期、线程范围的记忆，包括对话连续性、human-in-the-loop、时间旅行与容错 [1]。
- 触发 `interrupt()` 时，LangGraph 用持久化层保存图状态并等待恢复；使用 interrupt 需要 checkpointer（生产环境用持久型）以及配置中的 thread ID，使运行时知道从哪个状态恢复 [2]。
- `thread_id` 是 checkpointer 存取检查点的主键，也是恢复的持久游标：复用同一 `thread_id` 恢复同一检查点，新值则开启空状态的新线程；没有它，checkpointer 无法保存状态或在 interrupt 后恢复 [3][2]。恢复时必须使用与中断时相同的 thread ID [2]。
- `checkpoint_id` 用于定位线程内某个具体检查点（如 `get_state` 时指定）；不指定则返回该 `thread_id` 的最新检查点。`StateSnapshot` 的 config 同时含 `thread_id`、`checkpoint_ns`、`checkpoint_id`，`parent_config` 指向父检查点 [3]。

最小调用顺序：编译图时传入 checkpointer；调用时在 config 中给 `thread_id`；中断后以同一 `thread_id` 传入 `Command(resume=...)` 恢复 [2]。

**2. 跨线程偏好：store + user_id / memory_id**

- store 在图状态之外保存应用定义数据，用于长期、跨线程记忆，包括用户偏好、事实与共享知识；与保存整份线程范围图状态的 checkpointer 不同 [1][4]。
- 示例中记忆以元组命名空间 `(<user_id>, "memories")` 组织，`user_id` 作为该用户记忆的命名空间；命名空间可为任意长度、不必是用户专属 [4]。
- 条目键是 `memory_id`（示例用 uuid 生成），通过 `runtime.store.aput(namespace, memory_id, ...)` 写入 [4]。
- 新线程（如 `thread_id` 为 "2"）中只要 `user_id` 相同，仍可访问同一批记忆 [4]。因此 `user_id` 与线程级 `thread_id` 是不同标识，归属不同层。

**3. 边界与限制**

- `MemorySaver`/`InMemorySaver` 将检查点存于 RAM，进程重启后全部丢失；生产应使用持久型 checkpointer（如 PostgresSaver、SqliteSaver）[1]。
- `PostgresSaver` 的 `thread_id` 列长度有限，应保持在 255 字符以内 [1]。
- store 的 `namespace_prefix` 按前缀而非精确匹配；结果超过 `limit` 会被静默截断；默认排序依后端而异，需要顺序时应客户端按 `item.updated_at` 排序 [4]。

**取舍**：若只需同一会话暂停后继续，checkpointer 足够；若偏好须在新线程可见，必须另用 store，不能依赖线程级检查点。两者并用是多数应用的推荐方式 [1]。

**未覆盖**：本次可见材料未给出 store 条目过期/删除策略的完整说明，也未给出各后端一致性保证的细节；这些无法从现有材料确认。

## Sources

1. Persistence — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/persistence.mdx
2. Interrupts — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/interrupts.mdx
3. Checkpointers — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/checkpointers.mdx
4. Stores — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/stores.mdx
