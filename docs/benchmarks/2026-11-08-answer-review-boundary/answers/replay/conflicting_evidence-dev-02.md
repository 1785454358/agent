# conflicting_evidence-dev-02

Using only the frozen documentation, reconcile super-step checkpoint boundaries with durable per-task writes that avoid rerunning successful sibling nodes after a failure.

Component status: completed; error: None; new Provider calls: 1.

## 结论

冻结文档把两层持久化对齐在同一 super-step 上：完整检查点只在 super-step 边界提交，而每个节点完成时先以任务粒度写入 `checkpoint_writes`，链接到进行中的检查点 [1]。因此同一 super-step 内某节点失败时，已成功兄弟节点的写入已持久化，恢复该 super-step 时不重跑它们 [1]。

## 边界与写入的关系

- **super-step 边界**：每个 super-step 边界创建一个检查点；super-step 是图中所有被调度节点执行的一个 tick（可并行），顺序图 `START→A→B→END` 在输入、A、B 后各产生一个检查点，且只能从检查点（即 super-step 边界）恢复 [1]。
- **检查点内容**：包含该步状态通道值、下一步节点、配置（`thread_id`、`checkpoint_ns`、`checkpoint_id`）、元数据（`source`、`writes`、`step`）、创建时间、父检查点配置及 `PregelTask` 列表 [1]。
- **per-task 写入**：节点在 super-step 内完成时，输出作为任务条目写入 `checkpoint_writes`，每节点输出一行，存 `(task_id, channel, value)` 并链接到检查点；完整状态快照在 super-step 完成时才提交 [1]。

## 避免重跑的条件

失败发生在同一 super-step 内、且兄弟节点已成功完成时，其 pending writes 已被保存；从该 super-step 恢复即不重跑这些节点 [1]。判定依据是已持久化的任务写入，而非完整快照。

## 限制与取舍

- 任务写入不是完整 `StateSnapshot`，time travel 仍只能从 super-step 边界的完整检查点恢复 [1]。
- 节点级超时与错误处理器需 `langgraph>=1.2`（JS 为 `@langchain/langgraph>=1.4.0`）[2]。
- 失败溯源会被检查点化：节点失败后、处理器完成前进程崩溃，恢复时处理器看到相同 `NodeError` 上下文 [2]。

可见材料未说明哪些具体写入不保证持久，也未给出跨 super-step 的兄弟节点重跑规则；这些属本次材料未覆盖，不能据此推断文档整体缺失。

Unresolved gaps: []
