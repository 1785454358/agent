# comparison-dev-02

Using only the frozen documentation, compare exit, async and sync checkpoint durability for a long-running workflow exposed to process crashes.

Component status: completed; error: None; new Provider calls: 1.

针对暴露于进程崩溃的长运行工作流，三种检查点持久性模式按持久性从低到高比较如下[1]：

- **exit**：仅在图执行退出时持久化变更——无论是成功、出错还是因 human-in-the-loop 中断而退出。对长运行图性能最好，但中间状态不会保存，因此无法在执行中途从系统故障（如进程崩溃）中恢复[1]。
- **async**：在下一步执行期间异步持久化变更。性能与持久性较好，但存在小风险：若进程在执行期间崩溃，LangGraph 可能不会写入检查点[1]。
- **sync**：在下一步开始前同步持久化变更，确保继续执行前写入每个检查点，提供高持久性，代价是一些性能开销[1]。

结论：对进程崩溃场景，exit 不能恢复中途状态；async 有崩溃时漏写检查点的小风险；sync 持久性最高[1]。

Unresolved gaps: []
