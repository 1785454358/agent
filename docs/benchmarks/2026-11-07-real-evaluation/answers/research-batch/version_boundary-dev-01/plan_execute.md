# version_boundary-dev-01 / plan_execute

Using only the frozen documentation, state the package/version boundary for Python per-node timeouts and node-level error handlers without confusing the JavaScript requirement.

Status: completed; answered flag: True; response reason: None; model calls: 6; seconds: 31.758.

**结论：** Python 侧两项能力都属 `langgraph` 包，版本边界均为 `>=1.2`；JS/TS 侧对应要求是 `@langchain/langgraph>=1.4.0`，两者不可混用 [1]。

| 能力 | Python 包与版本 | JS/TS 包与版本 |
|---|---|---|
| per-node timeouts | `langgraph>=1.2` [1] | `@langchain/langgraph>=1.4.0` [1] |
| node-level error handlers | `langgraph>=1.2` [1] | `@langchain/langgraph>=1.4.0` [1] |

文档在总注中把两项能力合并声明 Python 要求 `langgraph>=1.2` [1]；Timeouts 与 Error handling 两章各自又重复注明同一版本边界 [1]，因此 Python 结论有双重支持。JS 注则单独写 `@langchain/langgraph>=1.4.0` [1]，不应把该版本号套到 Python 上。

**Python 适用条件：** 节点超时只适用于 async 节点；带 `timeout` 的同步节点会在编译时被拒绝，阻塞 I/O 需在 async 节点内用 `asyncio.to_thread` 包装 [1]。错误处理器通过 `add_node` 的 `error_handler=` 传入，可用类型注解注入可选的 `error: NodeError` 参数，也可用 `(state)` 或 `(state, runtime)` 等更简签名 [1]。

**文档未记载：** 除上述 async 限制与处理器签名方式外，冻结文档未给出 Python 这两项能力的其他运行模式限制或与 JS 的行为差异说明 [1]。JS 侧另注：`task`/`entrypoint` 上不提供错误处理器，应改用 `StateGraph.addNode(..., { errorHandler })` [1]——这是 JS 的边界，不是 Python 的。

## Sources

1. Fault tolerance — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/fault-tolerance.mdx
