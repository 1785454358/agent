# version_boundary-dev-02 / plan_execute

Using only the frozen documentation, on Python 3.10, what limitations apply to async LLM callback propagation and custom stream writers?

Status: completed; answered flag: True; response reason: None; model calls: 6; seconds: 29.312.

**结论：** 在 Python 3.10（属于文档所称“Python < 3.11”）上，冻结文档对两类用法都给出了显式限制：异步 LLM 回调/流式传播需手动传 `RunnableConfig`；自定义流写入器 `get_stream_writer` 在异步代码中不可用，需改为手动传 `writer` 参数 [1]。文档以“Python < 3.11”为条件声明，因此 3.10 明确落在适用范围内；但专门章节正文在可见材料中未展开 [1]。

**1. 异步 LLM 回调传播**

- 限制：在 Python < 3.11 上使用异步代码时，必须显式把 `RunnableConfig` 传给 `ainvoke()`，才能启用正确的流式输出 [1]。
- 适用条件：异步代码 + Python < 3.11；文档建议查看“Async with Python < 3.11”章节或升级到 Python 3.11+ [1]。
- 可见示例：异步节点函数接收 `config`，并把它作为第二个参数传给 `model.ainvoke(...)`，注释说明这是为了确保正确的上下文传播 [1]。

**2. 自定义流写入器**

- 限制：在 Python < 3.11 上运行的异步代码中，`get_stream_writer` 将无法工作 [1]。
- 替代做法：给节点或工具添加 `writer` 参数并手动传入 [1]。
- 适用条件：异步代码 + Python < 3.11；文档同样指向“Async with Python < 3.11”章节的用法示例 [1]。

**3. Python 3.10 的适用性**

- 文档显式以“Python < 3.11”声明上述两类限制，Python 3.10 属于该范围，因此可判定限制适用 [1]。
- 文档设有“Async with Python < 3.11”章节，但可见原文只给出标题和开头片段，未展示完整正文；该章节可能包含更多细节，但本次材料无法确认 [1]。

**取舍与边界：** 若运行环境可升级到 Python 3.11+，文档给出的路径是升级，从而避开这两项限制 [1]；若必须留在 3.10，则应按文档要求手动传 `config` 与 `writer`。以上仅为文档所述条件与做法，未对实际运行效果作验证。

## Sources

1. Streaming — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/streaming.mdx
