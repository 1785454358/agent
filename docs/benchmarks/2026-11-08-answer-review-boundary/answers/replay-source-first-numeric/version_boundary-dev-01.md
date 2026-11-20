# version_boundary-dev-01

Using only the frozen documentation, state the package/version boundary for Python per-node timeouts and node-level error handlers without confusing the JavaScript requirement.

Component status: completed; error: None; new Provider calls: 1.

按冻结文档，Python 的每节点超时与节点级错误处理器都要求 `langgraph>=1.2`，这是 Python 侧的包/版本边界[1]。文档在“Timeouts”小节同样注明 Python 需 `langgraph>=1.2`[1]；在“Error handling”小节也注明 Python 需 `langgraph>=1.2`[1]。

JavaScript/TypeScript 侧是另一条边界，不能与 Python 混用：每节点超时和节点级错误处理器要求 `@langchain/langgraph>=1.4.0`[1]；错误处理小节同样注明 JS 需 `@langchain/langgraph>=1.4.0`[1]。

因此结论是：Python 用 `langgraph>=1.2`，JavaScript/TypeScript 用 `@langchain/langgraph>=1.4.0`，两者包名和版本号均不同，不应把 JS 的 `>=1.4.0` 要求套到 Python 上[1]。

Unresolved gaps: []
