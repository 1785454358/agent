## 结论

按冻结文档，三者都是应对长对话超出上下文窗口的常见方案 [1]，但机制与持久性不同：**trimming** 是调用 LLM 前临时裁剪发送给模型的消息（transient，不改已保存状态）[1][2]；**deleting** 是从 LangGraph 状态中永久移除消息，适合删除特定消息或清空整个历史 [1]；**summarizing** 是把较早消息总结成摘要并**永久**替换进状态，供后续所有轮次使用，同时保留最近消息 [2]。文档没有给出三者之间的显式排序或组合使用指引，只明确对比了 transient trimming 与 persistent summarization [2]。

## 逐项对比

| 维度 | Trimming | Deleting | Summarizing |
|---|---|---|---|
| 机制 | 调用 LLM 前移除前/后 N 条消息；可按 token 计数在接近上限时截断，用 trim messages 工具指定保留 token 数与 strategy（如保留最后 max_tokens）[1] | 用 `RemoveMessage` 从图状态删除；要求状态键使用 `add_messages` reducer（默认 `AgentState` 已提供）[1] | `SummarizationMiddleware` 在超过 token 上限时自动：用一次独立 LLM 调用总结旧消息、在状态中永久替换为摘要、保留最近消息 [2] |
| 实现位置 | 中间件：Python 用 `@before_model` 装饰器，JS 用 `createMiddleware` 的 `beforeModel` 钩子 [1] | 图状态层面（reducer 机制）[1] | 内置中间件，可配置 `trigger`（如 tokens: 4000）与 `keep`（如保留 20 条）[2] |
| 持久性 | Transient：只改单次调用发给模型的内容，不改已保存状态 [2] | 永久：从状态中删除 [1] | 永久：状态被持久更新，未来轮次看到摘要而非原始消息 [2] |
| 适用场景 | 长对话超出上下文窗口时的常见方案 [1] | 想移除特定消息或清空整个消息历史时 [1] | 对话过长时自动压缩历史 [2] |

## 共同动机与取舍

文档指出，长对话可能放不进上下文窗口，导致上下文丢失或报错；即使模型支持完整上下文长度，多数 LLM 在长上下文上表现仍差——被陈旧/离题内容分散注意力，响应更慢、成本更高 [1]。这是三者共同要解决的问题。

有据可依的取舍：

- **信息保留**：summarizing 以摘要形式保留旧信息的要点，而 trimming/deleting 直接丢弃被移除的内容（文档只描述摘要"替换旧消息"，未承诺信息无损）[2]。
- **额外开销**：summarizing 需要一次独立的 LLM 调用 [2]；trimming/deleting 的文档描述中没有此类额外调用。
- **可逆性**：trimming 不动已保存状态，被裁掉的消息仍在状态中 [2]；deleting 与 summarizing 都是永久修改状态 [1][2]。

## 文档未覆盖之处

可见材料未给出：三者之间的显式选择排序、组合使用指引、摘要质量/信息损失的量化说明，以及 trimming 与 deleting 在效果上的直接对比。这些缺口仅说明本次可见材料不足，不能推断完整文档没有相关内容。