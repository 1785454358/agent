# version_boundary-dev-01

Using only the frozen documentation, state the package/version boundary for Python per-node timeouts and node-level error handlers without confusing the JavaScript requirement.

Component status: completed; error: None; new Provider calls: 1.

Python 的每节点超时（per-node timeouts）和节点级错误处理器（node-level error handlers）都要求 `langgraph>=1.2`[1]。文档在“Timeouts”一节同样注明 Python 需要 `langgraph>=1.2`[1]，在“Error handling”一节也注明 Python 需要 `langgraph>=1.2`[1]。这是 Python 包的版本边界，不应与 JavaScript/TypeScript 的要求混淆：JS 对应要求是 `@langchain/langgraph>=1.4.0`[1]。

Unresolved gaps: []
