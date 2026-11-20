# comparison-dev-02 / workflow

Using only the frozen documentation, compare exit, async and sync checkpoint durability for a long-running workflow exposed to process crashes.

Status: completed; answered: True; reason: None; model calls: 6; tools: 25; seconds: 33.723.

**结论：按崩溃持久性从弱到强为 exit < async < sync。** 冻结文档明确按此顺序排列，并分别说明崩溃场景下的行为 [1]。对长时间运行且可能遭遇进程崩溃的工作流，sync 提供最高持久性，async 有漏写检查点的小风险，exit 无法从执行中途崩溃中恢复 [1]。

| 模式 | 何时持久化 | 进程崩溃时 | 可能丢失 | 恢复 | 代价 |
|---|---|---|---|---|---|
| exit | 仅图执行退出时：成功、出错或人机交互中断 [1] | 中间状态未保存，无法从执行中途系统故障（如进程崩溃）恢复 [1] | 自上次退出以来全部已完成步骤 | 不能从崩溃点恢复 [1] | 长运行图性能最好 [1] |
| async | 在下一步执行期间异步持久化 [1] | 存在小风险：执行期间进程崩溃时可能未写入检查点 [1] | 崩溃时尚未落盘的那部分步骤 | 可回到最近已写入的检查点，但可能回退 [1] | 性能与持久性兼顾 [1] |
| sync | 在下一步开始前同步持久化 [1] | 继续执行前已写入每个检查点，提供高持久性 [1] | 至多当前未完成的一步 | 从最近检查点恢复，回退最小 [1] | 有一定性能开销 [1] |

**取舍与适用条件：** 文档未给出针对“长时间运行 + 进程崩溃”的单独推荐，只给出排序与各模式描述 [1]。据此可归纳（非原文直接推荐）：若崩溃恢复是硬要求，选 sync；若可接受少量回退以换取性能，选 async；exit 只适合能容忍崩溃后从头或从上次正常退出重来的长运行图 [1]。

**触发方式：** 在任意图执行方法调用时指定 `durability`，例如 `graph.stream({"input": "test"}, durability="sync")`（Python）或 `await graph.stream({ input: "test" }, { durability: "sync" })`（JS）[1]。

**边界：** 上述持久性还取决于所用 checkpointer 是否真正持久化；`MemorySaver`/`InMemorySaver` 将检查点存于内存，进程重启即全部丢失，生产应使用持久化 checkpointer [2]。文档未对三种模式给出量化性能数据或崩溃注入实验结果，无法据此验证实际丢失窗口大小。

## Sources

1. Checkpointers — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/checkpointers.mdx
2. Persistence — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/persistence.mdx
