# version_boundary-dev-02 / workflow

Using only the frozen documentation, on Python 3.10, what limitations apply to async LLM callback propagation and custom stream writers?

Status: partial; answered: False; reason: answer_review_incomplete; model calls: 6; seconds: 24.836.

**结论：在 Python 3.10 上，异步场景有两处明确限制。**（1）异步 LLM 流式输出必须显式把 `RunnableConfig` 传给 `ainvoke()`，否则无法正确流式输出；文档建议升级到 Python 3.11+ [1]。（2）异步代码中 `get_stream_writer` 不可用，自定义流写入需改为给节点或工具加 `writer` 参数并手动传入 [1]。

**异步 LLM 回调/配置传播**

- 条件：Python < 3.11 且使用异步代码 [1]。
- 限制：必须显式传 `RunnableConfig` 给 `ainvoke()` 才能启用正确流式输出 [1]。
- 原因（原文注释）：3.11 之前缺少 context var 支持，需显式传递以确保 context vars 正确传播 [1]。
- 取舍：文档给出的替代路径是升级到 Python 3.11+ [1]。

**自定义流写入器**

- 条件：Python < 3.11 的异步代码 [1]。
- 限制：`get_stream_writer` 不工作；应给节点或工具增加 `writer` 参数并手动传入 [1]。
- 触发方式：调用 `.stream()`/`.astream()` 时设 `stream_mode="custom"`；可组合多个模式，但至少一个须为 `"custom"` [1]。
- 用途边界：`custom` 模式可用于流式输出任意 LLM API 的数据，包括未实现 LangChain chat model 接口的 API [1]。

**未覆盖项**：本次可见材料未给出 Python 3.10 下回调传播的事件类型清单、嵌套调用约束，也未给出 `writer` 参数的具体签名或完整示例；这些不能由现有摘录确认 [1]。

## Sources

1. Streaming — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/streaming.mdx
