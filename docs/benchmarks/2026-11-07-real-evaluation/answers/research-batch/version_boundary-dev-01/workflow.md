# version_boundary-dev-01 / workflow

Using only the frozen documentation, state the package/version boundary for Python per-node timeouts and node-level error handlers without confusing the JavaScript requirement.

Status: completed; answered flag: True; response reason: None; model calls: 6; seconds: 25.968.

**结论：Python 侧两项功能都归 `langgraph` 包，版本边界为 `langgraph>=1.2`；JavaScript 侧是另一个包 `@langchain/langgraph`，边界为 `>=1.4.0`，两者不可混用。**

- **Python per-node timeouts**：属于 `langgraph`，文档明确写“Per-node timeouts and node-level error handlers require `langgraph>=1.2`”[1]。用法上通过 `langgraph.types.TimeoutPolicy` 在 `add_node` 传入 `timeout`[1]。
- **Python node-level error handlers**：同样属于 `langgraph`，同一句版本说明覆盖它[1]；处理器通过 `langgraph.errors.NodeError` 类型注解注入[1]。
- **JavaScript 对应要求**：文档在 JS 分支写“require `@langchain/langgraph>=1.4.0`”[1]，包名与版本号均不同于 Python 的 `langgraph>=1.2`。

**取舍与边界**：两项功能在 Python 侧共享同一条版本门槛，文档未给出更细的逐功能版本差异；因此只能表述为“两者均需 `langgraph>=1.2`”，不能推断某一项有独立版本。JS 侧 `>=1.4.0` 仅约束 `@langchain/langgraph`，不适用于 Python 安装。

**缺口**：本次可见材料只给出下限，未说明上限或具体发布版本号；无法据此确认更早版本是否部分可用。

## Sources

1. Fault tolerance — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/fault-tolerance.mdx
