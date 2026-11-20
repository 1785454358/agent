# version_boundary-dev-01 / workflow

Using only the frozen documentation, state the package/version boundary for Python per-node timeouts and node-level error handlers without confusing the JavaScript requirement.

Status: completed; answered: True; reason: None; model calls: 6; tools: 8; seconds: 24.798.

**结论：Python 的逐节点超时与节点级错误处理器要求 `langgraph>=1.2`；JavaScript/TypeScript 的对应能力要求 `@langchain/langgraph>=1.4.0`。两者是各自独立的包与版本边界，不能互相替代。[1]**

- Python：冻结文档在 `:::python` 区块中写明，逐节点超时和节点级错误处理器需要 `langgraph>=1.2`。[1]
- JavaScript/TypeScript：冻结文档在 `:::js` 区块中写明，对应能力需要 `@langchain/langgraph>=1.4.0`。[1]

**JS 侧额外限制**：在 JavaScript/TypeScript SDK 中，错误处理器不适用于 `task` / `entrypoint`，应改用 `StateGraph.addNode(..., { errorHandler })`。[1] 因此，JS 的版本边界只解决“是否支持”，不改变错误处理器的适用位置。

**取舍**：若项目使用 Python，按 `langgraph>=1.2` 判断；若使用 JS/TS，按 `@langchain/langgraph>=1.4.0` 判断，并注意上述 `addNode` 用法。不要把 JS 的 `1.4.0` 当作 Python 的版本要求，也不要把 Python 的 `1.2` 套到 JS 包上。[1]

本次可见材料只给出上述版本门槛与 JS 适用位置，未给出更细的版本差异或迁移步骤；这些内容无法从当前材料确认。

## Sources

1. Fault tolerance — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/fault-tolerance.mdx
