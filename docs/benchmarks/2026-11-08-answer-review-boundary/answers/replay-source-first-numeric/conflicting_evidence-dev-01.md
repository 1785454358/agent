# conflicting_evidence-dev-01

Using only the frozen documentation, reconcile 'checkpointing keeps your place' with 'interrupt resumption restarts the entire node'. Is the exact Python instruction pointer restored?

Component status: completed; error: None; new Provider calls: 1.

结论：不能把“checkpointing keeps your place”理解为恢复精确的 Python 指令指针。原文明确说，中断恢复时运行时会“restarts the entire node from the beginning—it does not resume from the exact line where interrupt was called”，因此 `interrupt()` 之前的代码会再次执行[1]。所以精确的 Python 指令指针（即中断发生的那一行）不会被恢复。

两句话可以这样调和：

1. “Checkpointing keeps your place”指的是线程/图状态的位置。checkpointer 会写入精确的图状态，以便之后恢复，即使处于错误状态；`thread_id` 是持久游标，复用同一 `thread_id` 会恢复同一 checkpoint，新值则开启空状态的新线程[1]。checkpointer 以 `thread_id` 为主键保存和检索 checkpoint；没有它，checkpointer 无法保存状态或在 interrupt 后恢复执行[2]。

2. 但恢复的粒度是节点，不是节点内的 Python 行。恢复时运行时从节点开头重启整个节点，不从中断调用所在行继续；因此中断前的代码会重跑[1]。节点内有多个 interrupt 时，恢复也从节点开头开始，按严格索引匹配任务中的 resume 值，所以 interrupt 调用的顺序很重要[1]。

3. checkpoint 的边界是 super-step。LangGraph 在每个 super-step 边界创建 checkpoint；只能从 checkpoint（即 super-step 边界）恢复执行[2]。节点级写入也会持久化：同一 super-step 中其他成功节点的 pending writes 会被保存，恢复时不必重跑这些成功节点[2]。这与“整个节点重启”并不矛盾：重启的是被中断的那个节点，而不是同一 super-step 中已成功完成的节点。

4. 故障恢复的表述同样是“从最后一个成功步骤重启图”，而不是恢复节点内部的指令位置[2]。

因此，精确的 Python 指令指针没有被恢复；被保留和恢复的是线程的图状态与 checkpoint 位置，而中断所在节点会从头执行。

Unresolved gaps: []
