# version_boundary-dev-01

Using only the frozen documentation, state the package/version boundary for Python per-node timeouts and node-level error handlers without confusing the JavaScript requirement.

Component status: completed; error: None; new Provider calls: 1.

**结论：** 冻结文档中，Python 的 per-node timeout 与 node-level error handler 同属 `langgraph` 包，版本边界均为 `langgraph>=1.2` [1]；JavaScript/TypeScript 侧是另一个包 `@langchain/langgraph>=1.4.0` [1]。两者包名与版本号不同，不可混用。

**Python 侧**

- per-node timeout：`add_node` 的 `timeout=` 参数，Timeouts 节标注 Requires `langgraph>=1.2` [1]。
- node-level error handler：Error handling 节同样标注 Requires `langgraph>=1.2` [1]。
- 文档开头的 Note 将两者合并表述为 require `langgraph>=1.2` [1]。

**JavaScript/TypeScript 侧（单独列出，避免混淆）**

- per-node timeout 与 node-level error handler 均要求 `@langchain/langgraph>=1.4.0` [1]。
- 该注记与 Python 注记在原文中并列出现，包名与版本号都不同 [1]。

**Python 侧使用条件（不改变版本边界）**

- 超时为 async-only：同步节点带 `timeout` 会在编译期被拒绝 [1]。
- 每个节点至多一个 `error_handler` [1]。
- 处理器自身抛错会向上传播，如同该节点没有处理器 [1]。
- `set_node_defaults` 不被子图继承，每个图独立管理自己的默认值 [1]。

Unresolved gaps: []
