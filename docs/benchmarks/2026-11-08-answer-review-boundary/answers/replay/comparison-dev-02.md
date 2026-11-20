# comparison-dev-02

Using only the frozen documentation, compare exit, async and sync checkpoint durability for a long-running workflow exposed to process crashes.

Component status: completed; error: None; new Provider calls: 1.

**结论：按进程崩溃下的检查点持久性，从弱到强为 exit < async < sync [1]。** 对长时间运行且可能遭遇进程崩溃的工作流，sync 持久性最高；async 存在崩溃时未写入检查点的小风险；exit 无法从执行中途的系统故障（如进程崩溃）恢复 [1]。

| 模式 | 何时持久化 | 进程崩溃时 | 恢复 | 代价 |
|---|---|---|---|---|
| exit | 仅在执行退出时：成功、出错或人机交互中断 [1] | 中间状态未保存，无法从执行中途崩溃恢复 [1] | 不能从崩溃点恢复 [1] | 长运行图性能最好 [1] |
| async | 在下一步执行期间异步持久化 [1] | 执行期间进程崩溃时，可能未写入检查点 [1] | 可回到最近已写入的检查点，可能回退 [1] | 性能与持久性兼顾 [1] |
| sync | 在下一步开始前同步持久化 [1] | 继续执行前已写入每个检查点，提供高持久性 [1] | 从最近检查点恢复，回退最小 [1] | 有一定性能开销 [1] |

**取舍：** 文档只给出上述排序与各模式描述，未针对“长时间运行 + 进程崩溃”给出单独推荐 [1]。据此可归纳（非原文直接推荐）：崩溃恢复为硬要求时选 sync；可接受少量回退换取性能时选 async；exit 只适合能容忍崩溃后从头或从上次正常退出重来的长运行图 [1]。

**触发方式：** 在任意图执行方法调用时指定 `durability`，如 `graph.stream({"input": "test"}, durability="sync")`（Python）或 `await graph.stream({ input: "test" }, { durability: "sync" })`（JS）[1]。

**边界：** 持久性还取决于 checkpointer 是否真正持久化；`MemorySaver`/`InMemorySaver` 将检查点存于内存，进程重启即全部丢失，生产应使用持久化 checkpointer [2]。文档未给出三种模式的量化性能数据或崩溃注入实验结果，无法据此量化实际丢失窗口大小 [1]。

Unresolved gaps: []
