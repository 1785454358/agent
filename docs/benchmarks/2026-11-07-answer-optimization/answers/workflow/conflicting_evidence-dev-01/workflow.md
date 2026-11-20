# conflicting_evidence-dev-01 / workflow

Using only the frozen documentation, reconcile 'checkpointing keeps your place' with 'interrupt resumption restarts the entire node'. Is the exact Python instruction pointer restored?

Status: completed; answered: True; reason: None; model calls: 6; seconds: 29.540.

**结论：不恢复精确的 Python 指令指针。** 冻结文档中的“checkpointing keeps your place”指保存并恢复图状态，而不是保存 Python 栈帧或代码行位置 [1]；中断恢复时运行时从节点开头重跑整个节点，`interrupt()` 之前的代码会再次执行 [1]。

**两者如何协调**

- “keeps your place”的“位置”是**图状态与 thread 游标**：检查点保存图状态快照，`thread_id` 是持久游标，复用它即恢复同一检查点 [1]。检查点按 super-step 边界创建，另以节点（任务）级写入持久化已完成节点的输出，完整快照在 super-step 完成时提交 [2]。
- “restarts the entire node”的“重启”是**节点执行起点**：恢复后从节点开头执行，不从中断行继续 [1]。
- 因此二者不矛盾：状态位置被保留，节点内代码位置不被保留。

**适用条件与边界**

- 中断（`interrupt()`）走 `GraphBubbleUp`，绕过重试与错误处理器，图正常暂停 [3]；恢复时整节点重跑 [1]。
- 故障恢复是另一机制：同一 super-step 中已成功节点的 pending writes 不会重跑 [2]，这与中断恢复的整节点重跑不同。
- 文档警告：单节点内 `while True` + `interrupt()` 会因每次恢复从头重跑而指数级重复执行 [1]；多中断按索引匹配恢复值，顺序须稳定 [1]。

**实践含义**：`interrupt()` 前的操作应幂等，副作用放在 `interrupt()` 之后或独立节点 [1]。

**缺口**：本次可见材料未给出底层运行时是否保存任何 Python 帧的说明；上述结论仅就文档明示的恢复语义而言。

## Sources

1. Interrupts — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/interrupts.mdx
2. Checkpointers — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/checkpointers.mdx
3. Fault tolerance — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/fault-tolerance.mdx
