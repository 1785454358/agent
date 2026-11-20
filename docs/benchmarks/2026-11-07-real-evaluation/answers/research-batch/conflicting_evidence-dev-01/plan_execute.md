# conflicting_evidence-dev-01 / plan_execute

Using only the frozen documentation, reconcile 'checkpointing keeps your place' with 'interrupt resumption restarts the entire node'. Is the exact Python instruction pointer restored?

Status: completed; answered flag: True; response reason: None; model calls: 6; seconds: 33.528.

**结论：不还原。** 冻结文档没有说恢复时还原精确的 Python 指令指针；相反，它明确说恢复时“从节点开头重启整个节点，而不是从调用 `interrupt()` 的确切行恢复”，因此 `interrupt()` 之前的代码会再次执行 [1]。所以“checkpointing keeps your place”中的“place”不是 Python 指令指针，而是图状态/线程游标层面的位置 [1]。

**两种表述如何协调**

- “keeps your place”指检查点器写入精确的图状态，以便之后恢复，即使处于错误状态；`thread_id` 是指向该状态的指针，用来告诉检查点器加载哪个状态 [1]。
- 检查点按 super-step 边界创建，保存的是图状态快照；节点（任务）级写入也会持久化，但不是完整的 `StateSnapshot` 检查点，时间旅行只能从 super-step 边界的完整检查点恢复 [2]。
- 中断恢复则在节点内部从节点开头重跑，而不是从 `interrupt()` 那一行继续 [1]。

因此二者作用于不同层级：**状态在 super-step 边界恢复，节点执行在节点级重启**，并不矛盾 [2][1]。

**边界与取舍**

- 文档只支持“图状态被保存并可恢复”这一层，未涵盖“还原 Python 指令指针” [1]。
- 由于节点会整体重跑，`interrupt()` 之前的代码会再次执行，文档据此要求：不要把 `interrupt` 包在 try/except 中、不要在节点内重排或条件性跳过 `interrupt` 调用、`interrupt` 前的操作应幂等、副作用放在 `interrupt` 之后或拆到单独节点 [1]。
- 同一 super-step 内已成功节点的写入可持久化，恢复时不必重跑这些成功节点；但这是节点级写入的容错行为，不等于恢复节点内部的指令指针 [2]。

**无法确认的部分**：本次可见材料没有给出任何“精确 Python 指令指针被保存/还原”的机制或字段；若要验证，应核查检查点实际保存的字段与恢复入口，而不是仅凭“keeps your place”推断。

## Sources

1. Interrupts — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/interrupts.mdx
2. Checkpointers — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/checkpointers.mdx
