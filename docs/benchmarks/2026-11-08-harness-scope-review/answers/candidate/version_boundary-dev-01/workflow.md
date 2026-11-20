# version_boundary-dev-01 / workflow

Using only the frozen documentation, state the package/version boundary for Python per-node timeouts and node-level error handlers without confusing the JavaScript requirement.

Status: completed; answered: True; reason: None; model calls: 7; tools: 9; seconds: 24.355.

**结论：Python 侧两项功能都由 `langgraph` 包提供，版本边界为 `langgraph>=1.2`；JavaScript 侧是另一个包 `@langchain/langgraph`，边界为 `>=1.4.0`，两者不可混用。**

- **per-node timeout（Python）**：`add_node` 的 `timeout=` 参数用于限制单次节点尝试的运行时长，文档在该节标注 Requires `langgraph>=1.2` [1]。
- **node-level error handler（Python）**：文档将 per-node timeouts 与 node-level error handlers 并列，统一标注 Python 需 `langgraph>=1.2` [1]。

**与 JavaScript 的区分**：同一处并列说明在 JS 分支标注 `@langchain/langgraph>=1.4.0` [1]；超时章节的 JS 示例同样标注该包与版本 [1]。因此 Python 的 `langgraph>=1.2` 不能套用到 JS，反之亦然。

**条件与边界**：Python 侧超时为 async-only，同步节点带 `timeout` 会在编译期被拒绝；每个节点最多一个 `error_handler`；handler 自身抛错会向上传播 [1]。这些是 Python 行为约束，不改变上述包/版本边界。

## Sources

1. Fault tolerance — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/fault-tolerance.mdx
