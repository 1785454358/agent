# comparison-dev-02

Using only the frozen documentation, compare exit, async and sync checkpoint durability for a long-running workflow exposed to process crashes.

Component status: completed; error: None; new Provider calls: 1.

结论：对长时间运行且可能遭遇进程崩溃的工作流，按原文给出的持久性从低到高为 exit < async < sync。exit 只在图执行退出时持久化变更（成功、出错或人工中断），中间状态不保存，因此无法从执行中途的系统故障（如进程崩溃）恢复[1]；async 在下一步执行期间异步持久化变更，性能与持久性较好，但若进程在执行期间崩溃，存在未写入检查点的小风险[1]；sync 在下一步开始前同步持久化变更，确保继续执行前写入每个检查点，持久性高但有一定性能开销[1]。三者可在调用任意图执行方法时通过 durability 参数指定，示例为 durability="sync"[1]。补充边界：内存型 MemorySaver/InMemorySaver 将检查点存于 RAM，进程重启后全部丢失，生产应改用持久化检查点器（如 PostgresSaver、SqliteSaver）[2]；异步运行图可用 InMemorySaver 或 AsyncSqliteSaver/AsyncPostgresSaver[1]。

Unresolved gaps: []
