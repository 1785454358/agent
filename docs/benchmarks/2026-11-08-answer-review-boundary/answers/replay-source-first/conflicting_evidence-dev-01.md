# conflicting_evidence-dev-01

Using only the frozen documentation, reconcile 'checkpointing keeps your place' with 'interrupt resumption restarts the entire node'. Is the exact Python instruction pointer restored?

Component status: completed; error: None; new Provider calls: 1.

两句话并不矛盾，但“恢复”的层次不同。检查点保存的是图状态，不是 Python 解释器的执行位置。

“Checkpointing keeps your place”指检查点器写入精确的图状态，使你可以稍后恢复，即使处于错误状态；`thread_id` 是持久游标，复用同一 `thread_id` 会恢复同一检查点，新值则开启空状态的新线程[n][1]。检查点在每个 super-step 边界创建，可从检查点（即 super-step 边界）恢复执行；节点级写入也会持久化，同一 super-step 中已成功节点的写入在恢复时无需重算[n][2]。

“中断恢复重启整个节点”指 `interrupt()` 被运行时捕获后，图保存当前状态并等待外部输入；恢复时运行时从节点开头重启整个节点，而不是从调用 `interrupt()` 的那一行继续，因此 `interrupt()` 之前的代码会再次执行[n][1]。多个 `interrupt` 的恢复值按严格索引匹配，所以节点内调用顺序必须一致，不能条件性跳过，也不能用非确定性的循环逻辑[n][1]。

因此，精确的 Python 指令指针不会被恢复。恢复的是检查点中的图状态和节点级写入；被中断的节点本身从头重跑。原文明确说不会从 `interrupt()` 所在精确行恢复[n][1]。

Unresolved gaps: []
