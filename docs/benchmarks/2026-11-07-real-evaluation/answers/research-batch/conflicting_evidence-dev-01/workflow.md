# conflicting_evidence-dev-01 / workflow

Using only the frozen documentation, reconcile 'checkpointing keeps your place' with 'interrupt resumption restarts the entire node'. Is the exact Python instruction pointer restored?

Status: completed; answered flag: True; response reason: None; model calls: 6; seconds: 33.512.

**结论：没有。冻结文档没有说明精确的 Python 指令指针被还原；按文档所述，中断恢复时节点从头重启，因此指令级位置不保留。**

两种说法并不矛盾，因为它们指的不是同一层级：

- **“Checkpointing keeps your place”** 的原文是“the checkpointer writes the exact graph state so you can resume later, even when in an error state”[1]。这里的“place”是**图状态（graph state）**，不是指令级状态。checkpoint 在每个 super-step 边界创建，并以 `thread_id` 作为持久游标加载状态[2][1]。
- **“Interrupt resumption restarts the entire node”** 的原文是：恢复时“The node restarts from the beginning of the node where the `interrupt()` was called when resumed, so any code before the `interrupt()` runs again”[1]；另一处更直接：“it does not resume from the exact line where `interrupt` was called”[1]。触发条件是使用**同一 thread ID** 并以 `Command(resume=...)` 恢复[1]。

| 维度 | checkpoint | interrupt 恢复 |
|---|---|---|
| 保留层级 | super-step / 任务级图状态[2] | 节点级执行[1] |
| 恢复粒度 | 从 checkpoint（super-step 边界）恢复[2] | 从节点开头重启[1] |
| 指令指针 | 未提及[1] | 明确不回到 `interrupt` 所在行[1] |

因此，“keeps your place”保留的是可恢复的图状态与进度位置，而节点内 Python 代码会从头重跑；**精确的 Python 指令指针既未被还原，文档也未作任何说明**——这属于文档未覆盖，而非可推断为“已还原”。

实际含义：`interrupt()` 之前的代码必须可安全重跑（文档建议把副作用放在 `interrupt()` 之后、使用幂等操作）[1]。

## Sources

1. Interrupts — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/interrupts.mdx
2. Checkpointers — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/checkpointers.mdx
