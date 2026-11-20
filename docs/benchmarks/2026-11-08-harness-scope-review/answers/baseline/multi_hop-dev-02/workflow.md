# multi_hop-dev-02 / workflow

Using only the frozen documentation, a node writes to an external service before interrupt(). How should resumption and duplicate side effects be handled?

Status: completed; answered: True; reason: None; model calls: 6; tools: 16; seconds: 39.919.

**结论：** 冻结文档明确要求，`interrupt()` 之前的外部写入应做成幂等操作，或把副作用移到 `interrupt()` 之后，或拆到独立节点；因为节点恢复时会从头重跑，`interrupt()` 之前的代码会被再次执行 [1]。文档没有给出通用的“恢复时跳过已执行前缀”机制，也没有提供内置去重键；检查点的 pending writes 只覆盖同一 super-step 内其他节点失败的情形，不覆盖单节点内 `interrupt()` 前的重跑 [2]。

**恢复语义。** 触发 `interrupt()` 时，LangGraph 用持久化层保存图状态并无限期等待；恢复时用 `Command` 重新调用图，其值成为节点内 `interrupt()` 的返回值 [1]。但节点是**从头重跑**的，不是从 `interrupt()` 那一行继续 [1]。文档用 `while True` + `interrupt()` 的警告说明这一点：每次恢复都会重放之前所有迭代，循环体代码呈指数级重复执行 [1]。

**重复副作用的机制与边界。** 若外部写入位于 `interrupt()` 之前，恢复重跑节点会再次调用该外部服务，可能覆盖首次更新或产生重复记录 [1]。`interrupt()` 通过 `GraphBubbleUp` 暂停，绕过重试策略和错误处理器 [3]，因此不能靠重试/错误处理去重。检查点按 super-step 边界创建，并按节点（任务）级持久化写入；同一 super-step 中其他节点失败时，已完成节点的写入已持久化，恢复时无需重跑这些成功节点 [2]。但这是跨节点的 pending writes 恢复，不改变单节点内 `interrupt()` 恢复时从头重跑的行为 [2]。

**文档给出的处理方式及条件：**

| 方式 | 文档依据 | 适用条件/限制 |
|---|---|---|
| 前置副作用幂等 | 明确建议 `interrupt` 前的副作用“应（理想上）幂等”，同一操作多次应用不改变首次执行后的结果 [1] | 需要外部服务支持幂等语义；文档是建议性表述，未给出具体幂等键 API |
| 副作用放到 `interrupt()` 之后 | 列为正确做法 [1] | 适用于副作用可在人工确认后执行的场景 |
| 副作用拆到独立节点 | 列为正确做法 [1] | 利用节点级检查点，避免同一节点重跑带入副作用；文档未展开跨节点失败时的全部边界 |
| 关键动作前用 `interrupt` 请求批准 | 文档建议在 API 调用、数据库变更等关键动作前暂停并请求批准 [1] | 把外部写入置于人工确认之后；仍需保证确认后执行本身不被重复触发 |
| 工具内放 `interrupt` | 工具每次被调用时暂停等待人工审核后再执行 [1] | 适用于工具调用型副作用；同样受节点重跑语义约束 |

**无法从当前材料确认的：** 文档未说明恢复时是否会跳过 `interrupt()` 之前的已完成调用、是否提供自动幂等键或事务性外部写入封装；这些需要额外核查持久化层与外部服务集成文档，不能由现有材料推断。

## Sources

1. Interrupts — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/interrupts.mdx
2. Checkpointers — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/checkpointers.mdx
3. Fault tolerance — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/fault-tolerance.mdx
