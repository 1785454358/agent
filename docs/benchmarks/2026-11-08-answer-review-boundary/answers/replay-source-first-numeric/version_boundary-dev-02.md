# version_boundary-dev-02

Using only the frozen documentation, on Python 3.10, what limitations apply to async LLM callback propagation and custom stream writers?

Component status: completed; error: None; new Provider calls: 1.

在 Python 3.10（即 Python < 3.11）上使用异步代码时，存在两项限制。

1. 异步 LLM 回调传播：必须显式把 `RunnableConfig` 传入异步 LLM 调用（如 `ainvoke()`），因为回调不会自动传播[1]。文档警告：在 Python < 3.11 配合异步代码时，必须显式向 `ainvoke()` 传递 `RunnableConfig` 才能正常流式输出；否则应升级到 Python 3.11+[1]。示例中同样注明，显式传 config 是为了确保上下文变量正确传播，这是 Python < 3.11 使用异步代码所必需的[1]。

2. 自定义流写入器：在 Python < 3.11 的异步节点或工具中不能使用 `get_stream_writer`，它不会工作；必须给节点或工具添加 `writer` 参数并手动传入[1]。

补充适用条件：若 LLM 不是 LangChain 集成，可用 `custom` 模式流式输出其结果[1]；使用自定义数据时需在 `.stream()`/`.astream()` 中设置 `stream_mode="custom"`，可与其他模式组合，但至少一个必须是 `"custom"`[1]。

Unresolved gaps: []
