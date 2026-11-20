# comparison-dev-02 / workflow

Using only the frozen documentation, compare exit, async and sync checkpoint durability for a long-running workflow exposed to process crashes.

Status: completed; answered: True; reason: None; model calls: 6; seconds: 26.881.

**结论：** 对暴露于进程崩溃的长运行工作流，持久性从低到高为 `exit` < `async` < `sync` [1]。`exit` 在崩溃中途无法恢复；`async` 有“可能未写入 checkpoint”的小风险；`sync` 在继续执行前确保每个 checkpoint 已写入 [1]。

| 模式 | 写入时机 | 进程崩溃时的持久性 |
|---|---|---|
| `exit` | 仅在图执行退出时（成功、出错或 human-in-the-loop 中断） | 中间状态不保存，执行中途崩溃无法恢复 [1] |
| `async` | 在下一步执行期间异步写入 | 性能与持久性较好，但进程执行期间崩溃时可能未写入 checkpoint [1] |
| `sync` | 在下一步开始前同步写入 | 确保继续执行前每个 checkpoint 都已写入，持久性高，但有性能开销 [1] |

**取舍：** 长运行图若最看重性能，`exit` 最好，但代价是崩溃后丢失全部中间进度 [1]；`async` 在性能与持久性间折中，但崩溃窗口内仍可能丢 checkpoint [1]；`sync` 持久性最高，适合不能接受崩溃丢失已写 checkpoint 的场景，代价是性能开销 [1]。

**边界：** 文档只给出上述定性保证与排序，未量化崩溃窗口、丢失步数或性能开销 [1]；也未说明不同 checkpointer 后端（如内存型在进程重启后全部丢失 [2]）与三种模式的组合差异。因此不能据此推断具体恢复点或指标。

## Sources

1. Checkpointers — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/checkpointers.mdx
2. Persistence — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/persistence.mdx
