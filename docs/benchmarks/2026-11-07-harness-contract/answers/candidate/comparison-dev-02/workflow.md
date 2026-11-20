# comparison-dev-02 / workflow

Using only the frozen documentation, compare exit, async and sync checkpoint durability for a long-running workflow exposed to process crashes.

Status: completed; answered: True; reason: None; model calls: 6; tools: 16; seconds: 30.168.

**结论：对暴露于进程崩溃的长时间运行工作流，持久性从低到高为 `exit` < `async` < `sync`。若要求崩溃后能从执行中途恢复，应选 `sync`；`async` 存在小概率丢失检查点风险；`exit` 无法从中途恢复。** [1]

| 模式 | 持久化时机 | 崩溃时行为 | 取舍 |
|---|---|---|---|
| `exit` | 仅在执行退出时（成功、出错或人工中断） | 中间状态不保存，无法从执行中途恢复 | 长运行图性能最好，但持久性最低 [1] |
| `async` | 下一步执行期间异步写入 | 执行期间崩溃可能未写入检查点，存在小风险 | 性能与持久性较好 [1] |
| `sync` | 下一步开始前同步写入 | 继续执行前已写入每个检查点 | 持久性高，有一定性能开销 [1] |

**条件与适用**：三种模式在调用任一图执行方法时指定，例如 `graph.stream({"input": "test"}, durability="sync")` [1]。对长运行且可能崩溃的工作流，`exit` 的“退出时持久化”不覆盖中途崩溃，故不能作为恢复依据；`async` 的异步写入窗口意味着崩溃可能落在未写入区间；`sync` 以每步前同步写入换取最高持久性 [1]。

**补充边界**：检查点能否跨进程重启保留还取决于检查点后端；`MemorySaver`/`InMemorySaver` 存于内存，进程重启后检查点全部丢失，生产应使用持久化检查点（如 `PostgresSaver`、`SqliteSaver`）[2]。因此选 `sync` 也需配合持久化后端，否则崩溃恢复仍不成立。

## Sources

1. Checkpointers — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/checkpointers.mdx
2. Persistence — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/persistence.mdx
