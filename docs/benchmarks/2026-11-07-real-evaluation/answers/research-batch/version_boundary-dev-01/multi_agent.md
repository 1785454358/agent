# version_boundary-dev-01 / multi_agent

Using only the frozen documentation, state the package/version boundary for Python per-node timeouts and node-level error handlers without confusing the JavaScript requirement.

Status: completed; answered flag: True; response reason: None; model calls: 6; seconds: 29.025.

**结论：Python 侧两项功能同属 `langgraph` 包，均要求 `langgraph>=1.2`；JavaScript 侧是另一个包、另一个版本线，要求 `@langchain/langgraph>=1.4.0`，两者不可混用。**

- **Python per-node timeouts**：包为 `langgraph`，版本 `>=1.2`。文档在总说明与 Timeouts 一节各标注一次 [1]。附加条件：节点超时仅适用于 **async** 节点，带 `timeout` 的同步节点会在编译期被拒绝；阻塞 I/O 需在 async 节点内用 `asyncio.to_thread` 包装 [1]。
- **Python node-level error handlers**：包为 `langgraph`，版本 `>=1.2`，Error handling 一节再次标注 [1]。
- **JavaScript 侧**：per-node timeouts 与 node-level error handlers 均要求 `@langchain/langgraph>=1.4.0`，文档以 `:::js` 块与 Python 的 `:::python` 块分别标注 [1]。另有使用边界：JS/TS SDK 中错误处理器不可用于 `task`/`entrypoint`，应改用 `StateGraph.addNode(..., { errorHandler })` [1]。

**取舍要点**：文档给出的是明确的包名加版本号，而非仅条件性说明；Python 的 `>=1.2` 与 JS 的 `>=1.4.0` 是两条独立要求，引用时须按语言分别对应，不能把 JS 版本号套到 Python 上。

**缺口**：本次可见材料未给出这两个版本号对应的具体发布日期或变更明细，无法据此判断更早版本是否部分可用；如需确认，应查对应版本的发布说明。

## Sources

1. Fault tolerance — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/fault-tolerance.mdx
