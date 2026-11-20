**结论：不够。** 短期消息历史只在单个 thread/会话内记住先前交互，并通过 checkpointer 维持不同 thread 之间的隔离 [1]；新会话线程中无法凭它召回持久偏好。需要跨会话记忆时应使用长期记忆 [1]。

**应配置的内容：**

1. **长期记忆 + Store**：长期记忆可跨不同会话与线程存取信息，底层基于 LangGraph store，数据以 JSON 文档按 namespace 和 key 组织 [2]。
2. **接入方式**：创建一个 store（如 `InMemoryStore`，生产可用 PostgreSQL，另有 Redis/MongoDB 等后端）并传给 `create_agent`；工具通过 `runtime.store` 参数读写 store [2]。
3. **存储结构**：每条记忆放在自定义 namespace（通常包含 user/org ID）加唯一 key 之下，便于按用户组织 [2]。
4. **读取方式**：用 `store.search(namespace)` 按用户命名空间取出记忆列表（默认 limit 10）；`InMemoryStore` 按插入顺序返回，最新在最后 [3]。

**取舍说明**：Store 与 checkpointer 不同——checkpointer 保存单个 thread 的完整图状态，store 保存任意线程可访问的键值数据（含用户偏好）[3]。若使用 Agent Server，则无需手动配置 store，API 自动处理存储基础设施 [3]。`InMemoryStore` 适合开发验证，生产环境应换数据库后端 [2][1]。

**依据边界**：以上仅基于所列冻结文档；具体代码片段（如 `create_agent` 调用示例）在资料中以引用占位符形式出现，未展示完整参数细节。