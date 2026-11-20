# version_boundary-dev-02 / multi_agent

Using only the frozen documentation, on Python 3.10, what limitations apply to async LLM callback propagation and custom stream writers?

Status: completed; answered flag: True; response reason: None; model calls: 9; seconds: 37.222.

**结论：** 在 Python 3.10（属于文档所称“Python < 3.11”）上，冻结文档只声明了两条限制：异步 LLM 回调/流式传播必须显式把 `RunnableConfig` 传给 `ainvoke()`；异步代码中 `get_stream_writer` 不可用，需手动传入 `writer` 参数 [1]。文档未单独区分 3.10 与其他版本，也未给出更多接口、缓冲或顺序层面的限制 [1]。

**1. 异步 LLM 回调传播**

文档警告：在 Python < 3.11 上使用异步代码时，必须显式向 `ainvoke()` 传入 `RunnableConfig` 才能启用正确的流式传播；否则异步流式无法正常工作，建议升级到 3.11+ [1]。示例注释给出的原因是该版本之前缺少 context var 支持，显式传 config 才能保证上下文变量正确传播 [1]。

因此 3.10 上的实际约束是：不能依赖隐式上下文传播，调用链中每个 `ainvoke()` 都要带上 config [1]。

**2. 自定义流写入器**

文档警告：在 Python < 3.11 的异步代码中，`get_stream_writer` 不会工作；替代做法是在节点或工具上增加 `writer` 参数并手动传入 [1]。使用自定义数据时还需设置 `stream_mode="custom"`（可与其他模式组合，但至少含 `"custom"`）[1]。

**3. 版本差异**

文档仅以“Python < 3.11”为界统一说明，未单独说明 3.10 与 3.11 以下其他版本的差异 [1]。

**缺口说明：** 本次可见材料未涉及自定义写入器的接口签名细节、缓冲/顺序行为或已知缺陷，也未说明回调类型层面的其他不支持场景；这些不能从现有材料确认 [1]。

## Sources

1. Streaming — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/streaming.mdx
