# single_hop-dev-01

Using only the frozen documentation, at what boundary does a LangGraph checkpointer create full state snapshots, and why must a thread_id be supplied?

Component status: partial; error: None; new Provider calls: 1.

**结论：** checkpointer 在**每个 super-step 边界**创建完整状态快照 [1]；调用带 checkpointer 的图时**必须**在 config 的 `configurable` 中提供 `thread_id`，因为 checkpointer 以它为主键保存/检索检查点，缺失时无法保存状态，也无法在 interrupt 后恢复执行 [1]。

**快照边界**

- super-step 是图的一次“tick”，该步调度的所有节点（可能并行）执行；顺序图 `START -> A -> B -> END` 在输入、节点 A、节点 B 后各产生一个检查点 [1]。
- 节点（任务）级写入只是 `checkpoint_writes` 中的任务条目，用于同一 super-step 内其他节点失败时的 pending writes 恢复，**不是**完整 `StateSnapshot`；完整快照在 super-step 完成时提交 [1]。
- 因此 time travel 只能从完整检查点（即 super-step 边界）恢复，不能从任务级写入恢复 [1]。

**为何必须 thread_id**

- 检查点按线程组织，checkpointer 持久化单个线程的图状态，用于线程范围内的短期记忆（对话连续性、human-in-the-loop、时间旅行、容错）；跨线程长期数据由 store 承担 [2]。
- `thread_id` 是存储和检索检查点的主键；没有它，checkpointer 无法保存状态，也无法在 interrupt 后恢复，因为恢复需要用 `thread_id` 加载已保存状态 [1]。

**适用条件与边界**

- 上述行为针对编译时传入 checkpointer 的图；使用 Agent Server 时持久化由服务端自动处理，无需手动配置 [2][1]。
- 默认每个 super-step 写入所有状态通道的完整值，长线程可能显著增长存储；`DeltaChannel` 可改为只存增量，但这是存储与延迟的取舍，不改变 super-step 边界语义 [1]。
- 本次可见材料未给出缺失 `thread_id` 时的具体报错文本或异常类型，无法确认该细节。

Unresolved gaps: ["可见材料未给出缺失 thread_id 时的具体报错文本或异常类型，无法确认该细节。"]
