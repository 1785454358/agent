# version_boundary-dev-02 / workflow

Using only the frozen documentation, on Python 3.10, what limitations apply to async LLM callback propagation and custom stream writers?

Status: completed; answered: True; reason: None; model calls: 6; tools: 8; seconds: 22.597.

**结论：在 Python 3.10 的异步代码中，冻结文档列出两项限制。** 第一，异步 LLM 调用（如 `ainvoke()`）不会自动传播回调，必须显式传入 `RunnableConfig`，否则流式输出无法正常启用 [1]。第二，异步节点或工具中不能使用 `get_stream_writer`，必须给节点或工具加 `writer` 参数并手动传入 [1]。文档建议升级到 Python 3.11+ 以避开这两项限制 [1]。

**条件与取舍**

- 这两项限制只针对“Python < 3.11 + 异步代码”这一组合；同步代码不受此约束 [1]。
- 自定义流式数据仍可用 `stream_mode="custom"` 获取，但异步下写入方式要改为手动传 `writer`，不能依赖 `get_stream_writer` [1]。
- 若 LLM 没有 LangChain 集成，文档建议用 `custom` 模式自行流式输出 [1]；这与上述 writer 限制是两件事，前者是接入方式，后者是 Python 3.10 异步下的传播/写入限制。

**实际意义**：在 3.10 上做异步流式时，需在每次异步 LLM 调用处显式携带配置，并在节点/工具签名中预留 `writer` 参数；否则回调与自定义数据可能静默缺失。文档未给出 3.10 下这两项限制的底层原因或性能影响，无法据此评估额外开销。

## Sources

1. Streaming — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/streaming.mdx
