# comparison-dev-02 / plan_execute

Using only the frozen documentation, compare exit, async and sync checkpoint durability for a long-running workflow exposed to process crashes.

Status: completed; answered flag: True; response reason: None; model calls: 6; seconds: 36.817.

**结论：按冻结文档的直接排序，持久性从低到高为 `exit` < `async` < `sync` [1]。对暴露于进程崩溃的长时运行工作流，`exit` 无法从中途崩溃恢复；`async` 有较小丢失窗口；`sync` 持久性最高但付出性能开销 [1]。**

| 模式 | 写入时机 | 崩溃时可能丢失的进度 | 恢复前提 | 取舍 |
|---|---|---|---|---|
| `exit` | 仅在执行退出时（成功、出错或人工中断）持久化 [1] | 执行中途的全部中间状态；文档明确“无法从中途系统故障（如进程崩溃）恢复” [1] | 只能从上次正常退出点继续 | 长时运行图性能最佳 [1] |
| `async` | 在下一步执行期间异步持久化 [1] | 崩溃时尚未写入的检查点，文档称“小风险” [1] | 从最近已写入的检查点恢复 | 性能与持久性较好 [1] |
| `sync` | 在下一步开始前同步写入每个检查点 [1] | 按文档表述，继续执行前每个检查点均已写入，持久性高 [1] | 从最近检查点恢复 | 有一定性能开销 [1] |

**条件与边界：**

- 三种模式通过图执行方法的 `durability` 参数选择，例如 `graph.stream({"input": "test"}, durability="sync")` [1]。
- 上述比较仅针对检查点写入时机与崩溃丢失窗口；文档未给出三种模式在具体崩溃概率、恢复耗时或吞吐量上的量化数据，无法据此做数值化排序。
- 检查点本身能否跨进程重启保留还取决于所选 checkpointer：`MemorySaver`/`InMemorySaver` 存于内存，进程重启后检查点全部丢失，生产环境应使用持久化后端 [2]。因此“`sync` 持久性高”是在检查点后端本身可持久化的前提下成立。
- 文档另提到 `DeltaChannel` 可减少检查点存储增长，但未将其与三种 durability 模式的崩溃行为直接关联 [1]。

**适用建议（基于上述文档事实）：** 若长时运行工作流可接受崩溃后从头或从退出点重来、优先性能，选 `exit`；若需在性能与崩溃恢复间折中，选 `async`；若崩溃后必须尽量从最近步骤恢复，选 `sync`，并配合持久化 checkpointer [2][1]。

## Sources

1. Checkpointers — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/checkpointers.mdx
2. Persistence — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/persistence.mdx
