# comparison-dev-02 / multi_agent

Using only the frozen documentation, compare exit, async and sync checkpoint durability for a long-running workflow exposed to process crashes.

Status: completed; answered flag: True; response reason: None; model calls: 5; seconds: 33.632.

**结论：按崩溃持久性从低到高为 exit < async < sync [1]。** 对长时间运行且可能进程崩溃的工作流，exit 无法从执行中途崩溃恢复；async 通常可恢复但存在“崩溃时检查点尚未写入”的小窗口；sync 在下一步开始前写入每个检查点，持久性最高但有一定性能开销 [1]。

| 模式 | 持久化时机 | 进程崩溃时可丢失的工作 | 恢复起点 |
|---|---|---|---|
| exit | 仅在图执行退出时（成功、出错或 human-in-the-loop 中断）[1] | 执行中途的全部中间状态；文档明确“无法从执行中途的系统故障（如进程崩溃）恢复”[1] | 无中途检查点可恢复；只能从头重跑（由“无法恢复”直接推出） |
| async | 在下一步执行期间异步写入 [1] | 崩溃时尚未写入的检查点，文档称“小风险”[1] | 最近一个已成功写入的检查点 |
| sync | 在下一步开始前同步写入 [1] | 按文档表述，继续执行前每个检查点都已写入，故崩溃前已完成步骤应已持久化 [1] | 最近一个已写入的检查点 |

**取舍与条件：** 文档明确三者用于在性能与数据一致性间权衡，并按持久性排序 exit、async、sync [1]。exit 为长运行图提供最佳性能，代价是中途不可恢复 [1]；async 兼顾性能与持久性，但接受崩溃窗口风险 [1]；sync 提供高持久性，代价是性能开销 [1]。文档未给出“必须选哪个”的硬性建议，只给出上述排序与权衡描述 [1]。

**补充边界：** 除超级步检查点外，LangGraph 还在节点（任务）级持久化：同一超级步内每个节点完成时其输出写入 `checkpoint_writes`，同超级步其他节点失败时已完成节点的写入已持久化、恢复时无需重跑；完整状态快照在超级步完成时提交 [1]。该机制影响“已完成节点”的重跑范围，但不改变上述三种模式在检查点写入时机上的差异 [1]。

**无法确认：** 冻结文档未量化 async 的崩溃窗口大小，也未给出各模式的性能开销数值；这些指标缺少测量输入，无法据现有材料验证 [1]。

## Sources

1. Checkpointers — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/checkpointers.mdx
