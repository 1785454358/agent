# comparison-dev-02 / baseline

Using only the frozen documentation, compare exit, async and sync checkpoint durability for a long-running workflow exposed to process crashes.

Status: completed; answered flag: True; response reason: None; model calls: 2; seconds: 14.082.

**结论：** 对暴露于进程崩溃的长运行工作流，按原文给出的耐久性排序（从最弱到最强）为 `exit`、`async`、`sync`。`exit` 只在图执行退出时（成功、报错或人工中断）持久化，中间状态不保存，因此无法从执行中途的系统故障（如进程崩溃）恢复 [1]；`async` 在下一步执行期间异步写入，性能与耐久性折中，但若进程在执行期间崩溃，存在未写入检查点的小风险 [1]；`sync` 在下一步开始前同步写入，确保继续执行前每个检查点都已写入，耐久性高，代价是性能开销 [1]。

| 模式 | 写入时机 | 进程崩溃时 | 取舍 |
|---|---|---|---|
| `exit` | 仅图执行退出（成功、报错或人工中断）时 [1] | 中间状态未保存，不能从执行中途恢复 [1] | 长运行图性能最好 [1] |
| `async` | 下一步执行期间异步写入 [1] | 执行期间崩溃可能未写入检查点 [1] | 性能好、耐久性较好 [1] |
| `sync` | 下一步开始前同步写入 [1] | 每个检查点都在继续执行前写入 [1] | 耐久性高，有性能开销 [1] |

**触发方式：** 在任意图执行方法上传入 `durability` 参数，例如 `graph.stream({"input": "test"}, durability="sync")` [1]。

**适用条件：** 若崩溃恢复是硬要求，选 `sync`；若可接受执行期间崩溃导致少量检查点丢失以换取性能，选 `async`；`exit` 适合不关心中途崩溃恢复、追求最佳性能的长运行图 [1]。

**边界说明：** 原文只给出上述三种模式的写入时机与崩溃风险，未提供各模式的恢复耗时、丢失步数上限等量化指标；这些需另行测量。另需注意，检查点默认每超级步写入所有状态通道的完整值，长线程可能显著增长存储，`DeltaChannel` 可只存增量以减小检查点体积 [1]，但这不改变上述耐久性语义。

## Sources

1. Checkpointers — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/checkpointers.mdx
