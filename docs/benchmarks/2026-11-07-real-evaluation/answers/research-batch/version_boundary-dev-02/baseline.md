# version_boundary-dev-02 / baseline

Using only the frozen documentation, on Python 3.10, what limitations apply to async LLM callback propagation and custom stream writers?

Status: completed; answered flag: True; response reason: None; model calls: 2; seconds: 12.086.

**结论：在 Python 3.10（<3.11）上，异步场景有两项明确限制：异步 LLM 调用不会自动传播回调，必须显式传入 `RunnableConfig`；异步节点/工具中不能使用 `get_stream_writer`，必须手动传入 `writer` 参数。** [1] 这两项都源于 Python <3.11 的 asyncio 任务不支持 `context` 参数，LangGraph 因此无法自动传播上下文 [1]。Python 3.10 属于该范围，故限制适用；升级到 3.11+ 可解除 [1]。

**1. 异步 LLM 回调传播**

- 限制：在异步 LLM 调用（如 `ainvoke()`）中，回调不会自动传播，必须显式把 `RunnableConfig` 传入调用 [1]。
- 条件：仅当使用 Python <3.11 且代码为异步时成立 [1]。
- 取舍：显式传 config 增加调用样板，但这是该版本下让流式/回调正常工作的必要条件；升级 Python 可省去该手工步骤 [1]。

**2. 自定义流写入器（custom stream writer）**

- 限制：`get_stream_writer` 在 Python <3.11 的异步代码中不工作；需给节点或工具加 `writer` 参数并手动传入 [1]。
- 条件：同样仅限 Python <3.11 的异步节点/工具 [1]。
- 替代路径：若 LLM 不是 LangChain 集成，可用 `custom` 流模式输出自定义数据 [1]；但异步下仍须走手动 `writer`，不能依赖 `get_stream_writer` [1]。

**适用边界**

上述两条是文档在“Async with Python <3.11”一节给出的全部相关限制 [1]。文档未在该节列出其他异步回调/写入器限制，故不宜外推。另需注意：父图默认不输出子图内 LLM 的 token，需 `subgraphs=True`，这与 Python 版本无关 [1]；节点超时仅适用于异步节点，同步节点带 `timeout` 会在编译期被拒绝 [2]，但这不是回调传播或流写入器的限制。

## Sources

1. Streaming — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/streaming.mdx
2. Fault tolerance — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/fault-tolerance.mdx
