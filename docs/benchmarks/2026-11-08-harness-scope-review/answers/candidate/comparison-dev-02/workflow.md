# comparison-dev-02 / workflow

Using only the frozen documentation, compare exit, async and sync checkpoint durability for a long-running workflow exposed to process crashes.

Status: completed; answered: True; reason: None; model calls: 5; tools: 19; seconds: 32.074.

**结论：** 按冻结文档的持久性排序，从低到高为 `exit`、`async`、`sync` [1]。对暴露于进程崩溃的长运行工作流：`exit` 无法从中途崩溃恢复；`async` 有“崩溃时未写检查点”的小风险；`sync` 持久性最高但有性能开销 [1]。文档未量化各模式丢失的进度量，也未针对崩溃场景给出明确推荐 [1]。

| 模式 | 写入时机 | 崩溃时持久性 | 代价/适用 |
|---|---|---|---|
| `exit` | 仅在执行退出时（成功、出错或 human-in-the-loop 中断）持久化 [1] | 中间状态不保存，无法从中途系统故障（如进程崩溃）恢复 [1] | 长运行图性能最好；崩溃会丢失自上次退出以来的未持久化进度 [1] |
| `async` | 在下一步执行期间异步持久化 [1] | 若进程在执行期间崩溃，可能未写入检查点，存在小风险 [1] | 性能与持久性较好；可能丢失尚未异步落盘的最近进度，文档未量化 [1] |
| `sync` | 在下一步开始前同步持久化 [1] | 确保继续执行前已写入每个检查点，提供高持久性 [1] | 有性能开销；文档未明确承诺崩溃时零丢失 [1] |

**取舍：** 追求长运行吞吐且可接受崩溃后从头/从上次退出重跑，选 `exit`；需要较好性能又希望降低崩溃丢失，选 `async`；崩溃恢复优先，选 `sync` [1]。

**缺口：** 冻结文档未给出崩溃场景的明确推荐，也未量化丢失进度 [1]；`sync` 的“高持久性”不等于文档承诺零丢失 [1]。另需注意，`MemorySaver`/`InMemorySaver` 将检查点存于内存，进程重启即全部丢失，生产应使用持久化 checkpointer [2]。

## Sources

1. Checkpointers — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/checkpointers.mdx
2. Persistence — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/persistence.mdx
