# version_boundary-dev-02 / workflow

Using only the frozen documentation, on Python 3.10, what limitations apply to async LLM callback propagation and custom stream writers?

Status: partial; answered: False; reason: answer_review_incomplete; model calls: 7; tools: 10; seconds: 31.723.

**结论：** 在 Python 3.10（属文档所称 Python < 3.11）上，异步 LLM 回调传播与自定义流写入器都受同一根因约束：异步上下文变量传播不完整。文档给出两条明确限制：异步调用 LLM 时必须显式传入 `RunnableConfig` 给 `ainvoke()`，否则流式传播不正确 [1]；异步代码中 `get_stream_writer` 不可用，需手动加 `writer` 参数并传入 [1]。文档建议升级到 Python 3.11+ [1]。

**异步 LLM 回调传播**

- 限制内容：Python < 3.11 的异步代码中，必须显式把 `RunnableConfig` 传给 `ainvoke()` 才能启用正确的流式输出 [1]。
- 触发条件：异步代码、Python < 3.11；文档示例在节点内对两个模型分别 `await ...ainvoke(..., config)`，并注释说明显式传 config 是为确保上下文变量正确传播 [1]。
- 例外/未支持：文档未列出其他例外；仅建议升级 3.11+ [1]。

**自定义流写入器**

- 限制内容：Python < 3.11 的异步代码中 `get_stream_writer` 不会工作 [1]。
- 替代做法：在节点或工具中手动添加 `writer` 参数并传入 [1]。
- 适用条件：自定义数据需通过 `get_stream_writer` 获取写入器，并在 `.stream()`/`.astream()` 时设 `stream_mode="custom"`；可与其他模式组合，但至少一个须为 `custom` [1]。
- 未支持情形：文档明确异步 + Python < 3.11 下 `get_stream_writer` 不可用 [1]；未说明同步写入、缓冲或并发行为的额外限制。

**与 Python 3.10 版本特性的关系**

文档以“Python < 3.11”为条件给出上述约束，3.10 属于该范围，故关系已说明 [1]。示例注释将原因指向 3.11 之前缺少上下文变量支持（context var support）[1]；这是文档注释的表述，未展开更多版本细节。

**缺口说明**：本次可见材料未给出回调层级、事件类型维度的细分限制，也未说明自定义写入器在缓冲/并发方面的行为；这些不能由现有材料推出。

## Sources

1. Streaming — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/streaming.mdx
