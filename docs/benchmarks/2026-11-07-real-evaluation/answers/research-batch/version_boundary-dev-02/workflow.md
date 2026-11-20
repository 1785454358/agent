# version_boundary-dev-02 / workflow

Using only the frozen documentation, on Python 3.10, what limitations apply to async LLM callback propagation and custom stream writers?

Status: completed; answered flag: True; response reason: None; model calls: 6; seconds: 28.716.

**结论：** 在 Python 3.10（属于文档所述“Python < 3.11”条件）上，异步 LLM 调用不会自动传播回调，必须显式传入 `RunnableConfig`；异步节点/工具中 `get_stream_writer` 不可用，必须手动传入 `writer` 参数 [1]。文档未单列 Python 3.10，而是以“Python < 3.11”为条件覆盖该版本 [1]。

**异步 LLM 回调传播**

- 限制：异步 LLM 调用（如 `ainvoke()`）中回调不会自动传播，必须显式把 `RunnableConfig` 传入调用，才能启用正确的流式输出 [1]。
- 适用条件：Python < 3.11 且使用异步代码；文档建议升级到 Python 3.11+ 或参考“Async with Python < 3.11” [1]。
- 取舍：升级可避开该限制；留在 3.10 则需在每个异步 LLM 调用处手动传配置，漏传会导致流式输出不正确 [1]。

**自定义 stream writer**

- 限制：在 Python < 3.11 的异步代码中，`get_stream_writer` 不工作 [1]。
- 替代做法：给节点或工具添加 `writer` 参数并手动传入，用该参数发出自定义数据 [1]。
- 输出侧条件：要接收自定义数据，调用 `.stream()` 时需设置 `streamMode: "custom"`，可与其他模式组合（如 `["updates", "custom"]`），但至少一个须为 `"custom"` [1]。
- 边界：`custom` 模式可用于任意 LLM API，包括未实现 LangChain chat model 接口的 API [1]；但上述 writer 限制针对 Python < 3.11 的异步场景 [1]。

**Python 3.10 专门说明**

文档没有单独点名 Python 3.10；其限制以“Python < 3.11”表述，因此 3.10 在范围内 [1]。除此之外，本次可见材料未给出 3.10 的其他专门前提或例外。

## Sources

1. Streaming — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/streaming.mdx
