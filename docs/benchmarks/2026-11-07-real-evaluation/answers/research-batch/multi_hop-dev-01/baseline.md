# multi_hop-dev-01 / baseline

Using only the frozen documentation, design memory for a user whose active conversation must resume after a pause and whose preferences must be available in a new thread. Which persistence mechanisms and identifiers belong where?

Status: partial; answered flag: False; response reason: answer_review_incomplete; model calls: 2; seconds: 14.766.

**结论：** 活跃对话的“暂停后恢复”应放在**线程级检查点（checkpointer）**中，以 `thread_id` 为主键；跨线程可用的偏好应放在**跨线程长期记忆存储（store）**中，以用户标识（如 `user_id`）为命名空间键。两者不能混用：检查点绑定单个线程，store 支持跨线程持久化 [1]。

**活跃对话恢复：checkpointer + thread_id**

- 检查点按 super-step 边界保存，可从中断处恢复执行 [1]。
- `thread_id` 是检查点存取的主键；没有它无法保存状态，也无法在中断后恢复 [1]。
- 恢复时必须复用同一 `thread_id`；换新值会开启空状态的新线程 [2]。
- 中断恢复用 `Command(resume=...)` 作为 `invoke` 输入，且节点会从头重跑，`interrupt` 前的副作用须幂等 [2]。
- 若用 Agent Server，检查点由服务端自动处理，无需手动配置 [1]。

**新线程可用偏好：store + 用户标识**

- 长期记忆 store 支持跨线程持久化，MongoDB 的 `MongoDBStore` 即属此类 [1]。
- 偏好写入 store 时以用户级键（如 `user_id`）组织，新线程读取同一键即可获得，不依赖旧 `thread_id`。
- 该键名与具体 store 实现细节，冻结文档未给出完整 API，需按所选 provider 的集成文档确认 [1]。

**取舍与边界**

| 维度 | checkpointer | store |
|---|---|---|
| 作用域 | 单线程 | 跨线程 |
| 主键 | `thread_id` | 用户级标识 |
| 用途 | 暂停/恢复、对话历史 | 偏好等长期事实 |
| 恢复条件 | 同一 `thread_id` | 同一用户键 |

注意：`thread_id` 复用即恢复同一检查点，新值即新线程 [2]；因此“新线程”场景必须靠 store 而非检查点携带偏好。检查点行键设计应保证按 `(thread_id, checkpoint_ns, checkpoint_id)` 直接查找，避免全表扫描 [1]。

## Sources

1. Checkpointers — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/checkpointers.mdx
2. Interrupts — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/interrupts.mdx
