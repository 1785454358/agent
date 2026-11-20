# comparison-dev-02

Using only the frozen documentation, compare exit, async and sync checkpoint durability for a long-running workflow exposed to process crashes.

Component status: completed; error: None; new Provider calls: 1.

针对暴露于进程崩溃的长时运行工作流，三种检查点持久化模式按持久性从低到高比较如下[1]：

- **exit**：仅在图执行退出时持久化变更——成功退出、因错误退出或因 human-in-the-loop 中断退出时均会写入。对长时运行图性能最好，但中间状态不会保存，因此无法从执行中途的系统故障（如进程崩溃）中恢复[1]。
- **async**：在下一步执行期间异步持久化变更。性能与持久性较好，但存在小风险：若进程在执行期间崩溃，LangGraph 可能未写入检查点[1]。
- **sync**：在下一步开始前同步持久化变更，确保继续执行前已写入每个检查点，提供高持久性，代价是一些性能开销[1]。

结论：对进程崩溃场景，exit 无法在中途崩溃后恢复；async 有较小概率丢失检查点；sync 持久性最高。三者均需配合持久化检查点后端；内存型 MemorySaver/InMemorySaver 在进程重启后会丢失全部检查点[2]。

Unresolved gaps: []
