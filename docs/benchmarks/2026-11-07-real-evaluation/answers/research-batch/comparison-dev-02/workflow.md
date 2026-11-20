# comparison-dev-02 / workflow

Using only the frozen documentation, compare exit, async and sync checkpoint durability for a long-running workflow exposed to process crashes.

Status: completed; answered flag: True; response reason: None; model calls: 6; seconds: 34.020.

**结论：** 按冻结文档，崩溃持久性从弱到强为 `exit` < `async` < `sync` [1]。长时间工作流若必须能从中途进程崩溃恢复，应选 `sync`；可接受崩溃时丢失尚未落盘检查点的小风险，选 `async`；`exit` 性能最好，但中途崩溃不可恢复 [1]。

**三种模式何时写入**

| 模式 | 写入/提交时机 | 崩溃时可能丢失 | 恢复起点 |
|---|---|---|---|
| `exit` | 仅图执行退出时：成功、出错或 human-in-the-loop 中断 [1] | 执行中途的中间状态全部未保存 [1] | 文档明确说无法从进程崩溃中恢复 [1] |
| `async` | 下一步执行期间异步持久化 [1] | 进程执行期间崩溃时，可能尚未写入的检查点 [1] | 从最近已成功写入的检查点恢复；文档未给出更细的丢失步数 [1] |
| `sync` | 下一步开始前同步写入每个检查点 [1] | 文档称“确保继续执行前检查点已写入”，未承诺零丢失 [1] | 从已写入的最近检查点恢复；文档未给出更细的恢复位置 [1] |

**取舍与适用条件**

- `exit`：文档称其为长时间运行图提供最佳性能，但明确不保存中间状态，因此不能用于需要崩溃恢复的长时间工作流 [1]。
- `async`：文档称性能与持久性兼顾，但存在“进程崩溃时未写检查点”的小风险 [1]。适合能容忍少量已完成工作重做的场景。
- `sync`：文档称持久性高，代价是性能开销 [1]。适合崩溃后必须尽量从最近检查点继续、不能接受未落盘检查点丢失的场景。

**限定：** 上述比较仅来自冻结文档的 durability modes 段落 [1]；文档没有给出各模式在崩溃时精确丢失的步数、恢复点编号或实测指标，不能据此量化“丢失多少已完成工作”。另外，检查点能否跨进程重启保留还取决于所选 checkpointer：`MemorySaver`/`InMemorySaver` 存于 RAM，进程重启后检查点全部丢失 [2]，此时讨论三种 durability 模式的崩溃持久性没有实际意义。

## Sources

1. Checkpointers — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/checkpointers.mdx
2. Persistence — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/persistence.mdx
