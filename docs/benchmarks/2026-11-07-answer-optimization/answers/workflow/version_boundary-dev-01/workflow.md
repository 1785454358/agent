# version_boundary-dev-01 / workflow

Using only the frozen documentation, state the package/version boundary for Python per-node timeouts and node-level error handlers without confusing the JavaScript requirement.

Status: completed; answered: True; reason: None; model calls: 6; seconds: 26.116.

**结论：** 在冻结文档中，Python 的 per-node timeout 与 node-level error handler 同属 Python 包 `langgraph`，版本下限均为 `1.2`，即要求 `langgraph>=1.2` [1]。JavaScript/TypeScript 的对应要求是 `@langchain/langgraph>=1.4.0`，属于另一个包，不能套用到 Python [1]。

**Python 边界**

- per-node timeout：Python 注释写明“Per-node timeouts and node-level error handlers require `langgraph>=1.2`” [1]；Timeouts 一节再次标注“Requires `langgraph>=1.2`”，示例从 `langgraph.types` 导入 `TimeoutPolicy` [1]。
- node-level error handler：Error handling 一节的 Python 注释同样标注“Requires `langgraph>=1.2`” [1]；示例从 `langgraph.errors` 导入 `NodeError` 作为处理器参数 [1]。

**与 JavaScript 的区分**

文档用 `:::python` 与 `:::js` 两个独立注释块分别给出要求：Python 为 `langgraph>=1.2`，JS 为 `@langchain/langgraph>=1.4.0` [1]。此外，文档说明在 JavaScript/TypeScript SDK 中，`task`/`entrypoint` 上不可用错误处理器，应改用 `StateGraph.addNode(..., { errorHandler })` [1]；该限制明确限定于 JS/TS，不应据此推断 Python 的用法或版本。

**适用条件**

上述版本边界仅来自冻结文档的注释与示例 [1]；文档未给出更细的补丁版本或向后兼容说明，无法据此确认其他版本行为。

## Sources

1. Fault tolerance — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/fault-tolerance.mdx
