# version_boundary-dev-01

Using only the frozen documentation, state the package/version boundary for Python per-node timeouts and node-level error handlers without confusing the JavaScript requirement.

Component status: completed; error: None; new Provider calls: 1.

Python 的每节点超时（per-node timeouts）和节点级错误处理器（node-level error handlers）要求 `langgraph>=1.2`[1]。文档在“Timeouts”与“Error handling”两处均以 Python 注记给出该边界[1]。JavaScript/TypeScript 的对应要求是 `@langchain/langgraph>=1.4.0`，属于另一包与另一版本，不应与 Python 的 `langgraph>=1.2` 混用[1]。

Unresolved gaps: []
