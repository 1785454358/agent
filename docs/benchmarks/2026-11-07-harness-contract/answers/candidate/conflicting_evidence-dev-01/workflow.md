# conflicting_evidence-dev-01 / workflow

Using only the frozen documentation, reconcile 'checkpointing keeps your place' with 'interrupt resumption restarts the entire node'. Is the exact Python instruction pointer restored?

Status: completed; answered: True; reason: None; model calls: 6; tools: 16; seconds: 29.726.

**结论：不恢复。** 检查点保留的是图状态与 super-step 位置，不是 Python 指令指针；中断恢复会从节点开头重跑整个节点。

**两种说法如何调和**

- “checkpointing keeps your place”指检查点写入精确的图状态，使你能用同一 `thread_id` 稍后恢复，即使处于错误状态 [1]；检查点在每个 super-step 边界创建，恢复只能从检查点（即 super-step 边界）开始 [2]。
- “interrupt resumption restarts the entire node”指恢复时运行时从节点开头重新启动，不从 `interrupt()` 所在行继续，`interrupt()` 之前的代码会再次执行 [1]。

**粒度对比**

| 维度 | 保留 | 不保留 |
|---|---|---|
| 图状态 | 是，检查点写入精确图状态 [1] | — |
| 恢复位置 | super-step 边界 [2] | 节点内部位置 [1] |
| Python 指令指针 | — | 不恢复，节点从头重跑 [1] |

**取舍与含义**

节点级重跑是设计使然：`interrupt()` 通过抛出异常暂停，恢复时按索引匹配 resume 值，因此要求 `interrupt` 调用顺序稳定、不条件跳过 [1]。实践上应把副作用放在 `interrupt()` 之后，或拆到独立节点，并把 `interrupt` 前的操作做成幂等 [1]。

**边界**

同一 super-step 内已成功完成的其它节点不会重跑，其写入已持久化 [2]；但被中断的那个节点本身仍从头执行 [1]。因此“保留位置”止于节点/super-step 边界，精确 Python 指令指针不在恢复范围内。

## Sources

1. Interrupts — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/interrupts.mdx
2. Checkpointers — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/checkpointers.mdx
