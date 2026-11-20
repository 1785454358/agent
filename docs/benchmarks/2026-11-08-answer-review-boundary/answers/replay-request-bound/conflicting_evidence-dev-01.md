# conflicting_evidence-dev-01

Using only the frozen documentation, reconcile 'checkpointing keeps your place' with 'interrupt resumption restarts the entire node'. Is the exact Python instruction pointer restored?

Component status: completed; error: None; new Provider calls: 1.

两句话并不矛盾，它们描述的是不同粒度。

“Checkpointing keeps your place”指检查点保存的是图状态（graph state）快照，使你能在之后从该检查点恢复，即使处于错误状态也可以[1]。检查点按 super-step 边界创建，恢复执行只能从检查点（即 super-step 边界）开始[2]；`thread_id` 是定位要加载哪份状态的指针[1]。因此“keeps your place”指的是线程/图状态层面的位置，而不是 Python 字节码层面的位置。

“Interrupt resumption restarts the entire node”指当 `interrupt()` 暂停后恢复时，运行时从节点开头重新执行整个节点，而不是从调用 `interrupt()` 的那一行继续；因此 `interrupt()` 之前已运行的代码会再次执行[1]。恢复时传给 `Command(resume=...)` 的值成为 `interrupt()` 调用的返回值[1]。

所以，精确的 Python 指令指针（instruction pointer）不会被恢复。文档明确说恢复时“restarts the entire node from the beginning—it does not resume from the exact line where `interrupt` was called”[1]。节点内多个 `interrupt` 的匹配严格按索引进行，这也要求节点内 `interrupt` 调用的顺序保持一致[1]。

补充边界：同一 super-step 内其他已成功完成节点的写入会被持久化，恢复时不会重跑这些成功节点[2]；但发生中断的那个节点本身仍从头重跑[1]。

Unresolved gaps: []
