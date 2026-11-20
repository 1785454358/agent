## 结论

**checkpoint 是“线程内的状态快照”，Store 是“跨线程的键值长期记忆”**。checkpoint 以 `thread_id` 为指针，保存图状态（含 channel 值、待处理任务等），用于恢复同一线程、interrupt 续跑和容错；Store 以自定义 `namespace` + `key` 组织任意数据，供任意线程读写，用于跨会话/跨用户长期记忆 [1][2][3]。

取舍：需要“接着上次继续跑”用 checkpointer；需要“换个线程仍记得”用 Store。二者可同时编译进图 [3]。

## 表格比较

| 维度 | checkpoint / checkpointer | Store |
|---|---|---|
| 用途 | 持久化图状态，支持恢复、interrupt、容错 [1] | 存任意信息供跨线程访问，长期记忆 [2][3] |
| 组织方式 | 以 `thread_id` 为指针 [1] | 自定义 `namespace` + `key`，JSON 文档 [2] |
| 线程边界 | 线程范围，线程间隔离 [2] | 跨线程，按 namespace 共享 [2][3] |
| 启用方式 | `builder.compile(checkpointer=...)` [3] | `builder.compile(store=...)` [3] |
| 节点访问 | 由运行时按 config 自动加载 | `Runtime.store` 或 `store: BaseStore` 参数 [2][3] |
| 恢复能力 | 同 `thread_id` 恢复同一 checkpoint [1] | 不参与图状态恢复，仅提供数据 |

## 三种场景

**进程重启**
- 事实：checkpointer 保存精确图状态以便稍后恢复；生产建议用数据库等持久化后端 [1]。复用同一 `thread_id` 恢复同一 checkpoint，新值则开空状态新线程 [1]。
- 前提：持久化后端 + 相同 `thread_id`。相同图结构/版本这一条，可见原文未明确说明，属**无法确认**。
- Store：可见原文只展示 `InMemoryStore` 用法 [3]，**未说明**各 Store 实现重启后数据是否保留，属**无法确认**；不能据常识断言持久化 Store 一定保留。

**interrupt 恢复**
- 事实：`interrupt()` 暂停时用 checkpointer 保存状态；恢复需相同 `thread_id`，`Command(resume=...)` 的载荷成为 `interrupt()` 返回值 [1]。
- 前提：配置 checkpointer（生产用持久化）、config 中有 thread ID [1]。
- Store 角色：可见原文**未说明** Store 参与中断恢复；其定位是跨线程额外数据 [3]。推断：Store 只能为恢复后的节点提供上下文，不承担断点恢复。

**跨线程共享**
- checkpoint：状态按线程隔离，不同线程保持分离 [2]；可见原文未提供跨线程共享 checkpoint 状态的机制。
- Store：新线程只要 `user_id` 相同仍可访问同一记忆 [3]；namespace 常含 user/org ID，支持跨 namespace 内容过滤检索 [2]。
- 并发访问与读写一致性的明确表述在可见原文中不足，属**无法确认**。

## 适用场景

- 用 checkpointer：多轮会话记忆、human-in-the-loop 审批、出错后恢复、时间旅行（后两者为官方列出的典型用途，时间旅行细节本次原文未展开）。
- 用 Store：跨会话用户偏好、跨用户/跨线程共享资料、few-shot 示例与可迭代的提示词 [2][3]。
- 组合：checkpointer 管“这次对话走到哪”，Store 管“这个用户长期是谁” [3]。

## 来源

- [1] Interrupts：https://docs.langchain.com/oss/python/langgraph/interrupts
- [2] Memory overview：https://docs.langchain.com/oss/python/concepts/memory
- [3] Stores：https://docs.langchain.com/oss/python/langgraph/stores

## 缺口说明

以上“无法确认”仅指本次可见材料不足，不代表官方文档整体无答案。建议核查：各 Store 实现的持久化语义、checkpoint 跨版本兼容条件、Store 并发一致性文档。
