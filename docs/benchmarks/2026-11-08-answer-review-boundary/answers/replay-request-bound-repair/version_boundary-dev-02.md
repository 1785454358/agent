# version_boundary-dev-02

Using only the frozen documentation, on Python 3.10, what limitations apply to async LLM callback propagation and custom stream writers?

Component status: completed; error: None; new Provider calls: 1.

在 Python 3.10 上使用异步代码时，文档列出两项限制：1）必须显式将 `RunnableConfig` 传入异步 LLM 调用（如 `ainvoke()`），因为回调不会自动传播[1]；2）不能在异步节点或工具中使用 `get_stream_writer`，必须直接传入 `writer` 参数[1]。文档还说明，在 Python < 3.11 的异步代码中 `get_stream_writer` 不会工作，应改为给节点或工具添加 `writer` 参数并手动传入[1]。

Unresolved gaps: []
