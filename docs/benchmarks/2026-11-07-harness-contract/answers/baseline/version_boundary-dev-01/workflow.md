# version_boundary-dev-01 / workflow

Using only the frozen documentation, state the package/version boundary for Python per-node timeouts and node-level error handlers without confusing the JavaScript requirement.

Status: completed; answered: True; reason: None; model calls: 6; tools: 9; seconds: 26.083.

**结论：** 在冻结文档中，Python 的 per-node timeout 与 node-level error handler 同属 `langgraph` 包，版本边界均为 `langgraph>=1.2` [1]；JavaScript/TypeScript 侧则是另一个包 `@langchain/langgraph>=1.4.0` [1]。两者不可混用版本号。

**Python 侧**

- per-node timeout：`add_node` 的 `timeout=` 参数，要求 `langgraph>=1.2` [1]。
- node-level error handler：Error handling 节同样标注 Requires `langgraph>=1.2` [1]。
- 额外依赖：文档未提及需要 `langgraph-checkpoint` 或独立 timeout 包 [1]；这只能说明本次可见材料未列出，不能据此断言全领域无此依赖。

**JavaScript/TypeScript 侧（单独列出，避免混淆）**

- per-node timeout 与 node-level error handler 均要求 `@langchain/langgraph>=1.4.0` [1]。
- 该注记与 Python 注记在原文中并列出现，包名与版本号都不同 [1]。

**取舍与条件**

按语言选包：Python 用 `langgraph>=1.2`，JS/TS 用 `@langchain/langgraph>=1.4.0` [1]。文档另给出 Python 侧边界：同步节点带 `timeout` 会在编译期被拒绝，即超时为 async-only；每个节点至多一个 `error_handler`；处理器自身抛错会向上传播；`set_node_defaults` 不被子图继承 [1]。这些是使用条件，不改变上述版本边界。

## Sources

1. Fault tolerance — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/fault-tolerance.mdx
