# version_boundary-dev-01 / baseline

Using only the frozen documentation, state the package/version boundary for Python per-node timeouts and node-level error handlers without confusing the JavaScript requirement.

Status: completed; answered flag: True; response reason: None; model calls: 2; seconds: 9.552.

**结论：Python 侧的门槛是 `langgraph>=1.2`，与 JavaScript 的 `@langchain/langgraph>=1.4.0` 是两个独立边界，不能互相套用。** 冻结文档在 Python 段落中明确写明：逐节点超时（per-node timeouts）和节点级错误处理器（node-level error handlers）需要 `langgraph>=1.2` [1]；紧接着的 JavaScript 段落则要求 `@langchain/langgraph>=1.4.0` [1]。因此，若问的是 Python 包，答案只取 `langgraph>=1.2`，不应把 `1.4.0` 当作 Python 版本要求，也不应把 `@langchain/langgraph` 当作 Python 包名 [1]。

条件与取舍：该版本边界只覆盖这两项能力（逐节点超时、节点级错误处理器），文档没有给出 Python 侧其他相关能力（如重试策略、缓存策略、图级默认值）的版本门槛，不能由本条外推 [1]。JavaScript 段落另有一处说明：错误处理器在 JS/TS SDK 的 `task`/`entrypoint` 上不可用，应改用 `StateGraph.addNode(..., { errorHandler })` [1]；这是 JS 侧的使用限制，不构成对 Python 的约束，回答 Python 问题时不应混入。

实际意义：在 Python 项目中启用这两项能力前，应核对已安装的 `langgraph` 版本不低于 1.2；若项目同时使用 JS/TS 包，则需分别按 `@langchain/langgraph>=1.4.0` 校验，两套版本号不可互换 [1]。

## Sources

1. Fault tolerance — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/fault-tolerance.mdx
