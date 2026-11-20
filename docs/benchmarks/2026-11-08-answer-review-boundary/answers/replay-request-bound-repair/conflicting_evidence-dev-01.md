# conflicting_evidence-dev-01

Using only the frozen documentation, reconcile 'checkpointing keeps your place' with 'interrupt resumption restarts the entire node'. Is the exact Python instruction pointer restored?

Component status: completed; error: None; new Provider calls: 1.

可以调和，但“位置”不是 Python 指令指针。

- “Checkpointing keeps your place”指检查点保存的是**图状态快照**，用于之后恢复线程状态；`thread_id` 是加载该状态的指针[1]。检查点按 super-step 边界创建，恢复执行只能从检查点（即 super-step 边界）开始[2]。
- 中断恢复时，运行时**从节点开头重新启动整个节点**，不会从调用 `interrupt()` 的那一行继续；因此 `interrupt()` 之前已运行的代码会再次执行[1]。
- 所以，被恢复的是图状态与 super-step 边界位置，而不是节点内部的精确执行位置。

**是否恢复精确的 Python 指令指针？** 否。文档明确说恢复时“restarts the entire node from the beginning—it does not resume from the exact line where `interrupt` was called”[1]。因此不存在精确 Python 指令指针的恢复；节点内进度需靠幂等操作、把副作用放在 `interrupt()` 之后等规则来保证正确性[1]。

Unresolved gaps: []
