**结论**：三种方法都用于解决长对话超出 LLM 上下文窗口的问题，但核心区别在于**持久性**和**信息保留方式**：Trimming 是**临时性**的（Transient，仅在调用 LLM 前处理，不永久改变状态），Deleting 是**永久性删除**（从图状态中彻底移除特定消息），Summarizing 是**永久性替换**（用摘要替换旧消息，保留核心信息）[1][2]。

## 机制对比

| 维度 | Trimming | Deleting | Summarizing |
|------|----------|----------|-------------|
| **持久性** | 临时（Transient） | 永久（Persistent） | 永久（Persistent） |
| **操作对象** | 发送给 LLM 的消息 | 图状态（Graph State）中的消息 | 图状态中的消息 |
| **实现方式** | `trim_messages` 工具或 `@before_model` 中间件 | `RemoveMessage` 配合 `add_messages` reducer | `SummarizationMiddleware` |
| **触发时机** | 每次调用 LLM 前 | 显式调用时 | 超过 token 限制时自动触发 |
| **信息去向** | 被截断的消息不发送给 LLM，但状态保持完整 | 被永久移除 | 被摘要替换，原始内容丢失 |

## 详细机制与适用场景

**Trimming（修剪）**
- **机制**：在调用 LLM 前，根据 token 计数移除消息列表的开头或结尾 N 条消息。使用 `trim_messages` 工具并指定 `strategy`（如保留最后 `max_tokens`），或通过 `@before_model` 中间件（Python）/ `createMiddleware` 的 `beforeModel` 钩子（JS）实现 [1]。
- **适用场景**：适合**临时性**控制上下文长度，保留完整历史在状态中以供后续使用。适用于需要灵活调整上下文窗口，但不想永久丢失任何消息的场景 [1][2]。

**Deleting（删除）**
- **机制**：使用 `RemoveMessage` 从图状态中永久移除特定消息或清空全部历史。要求状态键必须配置 `add_messages` reducer 才能生效 [1]。
- **适用场景**：适合**精确控制**状态内容，如移除敏感信息、错误消息或完全重置对话 [1]。

**Summarizing（总结）**
- **机制**：当对话超过 token 限制时，`SummarizationMiddleware` 自动触发，使用单独的 LLM 调用将旧消息压缩为摘要，并用该摘要**永久替换**状态中的原始消息，同时保留最近的消息不变 [2]。
- **适用场景**：适合**长期对话**需要保留历史上下文但受限于 token 的情况。通过牺牲细节保留核心信息，平衡上下文长度与信息完整性 [2]。

## 关键取舍

1. **状态一致性**：Trimming 不改变持久化状态，状态保持完整；Deleting 和 Summarizing 会永久改变状态，影响所有后续轮次 [1][2]。
2. **信息保留**：Trimming 和 Deleting 都会丢失被移除消息的详细内容；Summarizing 保留核心信息但丢失细节 [2]。
3. **实现复杂度**：Trimming 相对简单（客户端截断）；Deleting 需要正确配置 reducer；Summarizing 需要额外 LLM 调用生成摘要 [1][2]。

**选择建议**：
- 需要**灵活调整**且保留完整历史 → Trimming
- 需要**精确移除**特定内容或重置对话 → Deleting  
- 需要**长期维护**对话且接受信息压缩 → Summarizing