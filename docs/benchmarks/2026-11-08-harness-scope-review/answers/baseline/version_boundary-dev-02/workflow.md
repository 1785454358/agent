# version_boundary-dev-02 / workflow

Using only the frozen documentation, on Python 3.10, what limitations apply to async LLM callback propagation and custom stream writers?

Status: completed; answered: False; reason: insufficient_evidence; model calls: 11; tools: 13; seconds: 40.216.

**结论：** 在 Python 3.10 的异步代码中，冻结文档列出两项限制：异步 LLM 调用必须显式传入 `RunnableConfig`，否则回调不会自动传播；`get_stream_writer` 不可用，须改为手动传入 `writer` 参数 [1]。两项限制均以“Python < 3.11”为条件，3.10 属于该范围 [1]。

**异步 LLM 回调传播**

- 限制内容：回调不会自动传播，必须显式把 `RunnableConfig` 传给异步 LLM 调用（如 `ainvoke()`），才能启用正确的流式输出 [1]。
- 触发条件：Python < 3.11 且使用异步代码 [1]。文档给出的原因是该版本之前缺少 context var 支持，需显式传 config 以保证上下文变量正确传播 [1]。
- 文档建议：按上述方式传 config，或升级到 Python 3.11+ [1]。

**自定义流写入器**

- 限制内容：异步代码中 `get_stream_writer` 无法工作 [1]。
- 替代方式：在节点或工具上添加 `writer` 参数并手动传入 [1]。
- 触发条件：同样是 Python < 3.11 的异步代码 [1]。

**两项之间的交互**

本次可见材料分别列出两项限制，但未说明它们之间的交互限制或相互影响 [1]。该缺口仅表示当前可见材料不足，不能据此推断全部文档没有相关说明。

**Python 3.10 限定**

文档以“Python < 3.11”表述，未单独点名 3.10；3.10 落在该区间内，故适用 [1]。

## Sources

1. Streaming — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/streaming.mdx
