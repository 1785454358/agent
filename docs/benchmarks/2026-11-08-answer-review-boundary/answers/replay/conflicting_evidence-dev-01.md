# conflicting_evidence-dev-01

Using only the frozen documentation, reconcile 'checkpointing keeps your place' with 'interrupt resumption restarts the entire node'. Is the exact Python instruction pointer restored?

Component status: completed; error: None; new Provider calls: 1.

**结论：不还原。** 冻结文档中“checkpointing keeps your place”保存的是图状态快照，不是 Python 执行栈或字节码位置；恢复时从节点开头重跑，因此精确的 Python 指令指针没有被证实还原，文档明确否定从 `interrupt()` 所在行继续 [1][2]。

**“keeps your place”指什么**

- checkpointer 在每个 **super-step** 边界保存一份图状态快照，按 `thread_id` 组织成线程 [1]。
- 恢复只能从检查点（即 super-step 边界）开始，不能从 super-step 内部任意位置恢复 [1]。
- 同一 super-step 内已成功节点的写入以 task 形式持久化，恢复时不必重算；但这些 task 写入不是完整 `StateSnapshot` [1]。

所以“place”是**逻辑进度**（哪个 super-step、哪些节点已完成），不是执行栈帧或指令偏移。

**“restarts the entire node”指什么**

- 恢复执行时，运行时从节点开头重启整个节点，不从 `interrupt()` 精确行继续；`interrupt()` 之前的代码会再次执行 [2]。
- 多个 `interrupt()` 时，恢复值按索引匹配，节点仍从头开始 [2]。

**两者如何调和**

| 维度 | checkpointing | interrupt 恢复 |
| ---- | ---- | ---- |
| 保存/恢复粒度 | super-step 边界的图状态快照 [1] | 节点级：整个节点从头重跑 [2] |
| 是否保留执行栈 | 否，文档未提及 [1] | 否，明确不从精确行恢复 [2] |
| 精确指令指针 | 未证实 | 未证实，且被否定 [2] |

二者不矛盾：检查点保证**图级进度**可续，节点内**代码级位置**不保留。恢复时图从检查点继续，但当前节点整体重入。

**精确 Python 指令指针是否还原？**

否，至少冻结文档未证实。文档未说明还原字节码偏移或帧位置；相反明确说重启整个节点、不从 `interrupt()` 行继续 [2]。因此 `interrupt()` 前的代码会重跑，副作用需幂等或放到 `interrupt()` 之后 [2]。

**边界**：以上仅基于本次可见的冻结文档；未覆盖其他实现或未来版本是否改变该行为。

Unresolved gaps: []
