# multi_hop-dev-02 / plan_execute

Using only the frozen documentation, a node writes to an external service before interrupt(). How should resumption and duplicate side effects be handled?

Status: completed; answered flag: True; response reason: None; model calls: 6; seconds: 36.137.

**结论：恢复时节点会从头重跑，`interrupt()` 之前的外部写入会被重复执行；冻结文档没有提供自动去重，要求使用者自行把该写入做成幂等，或把它移到 `interrupt()` 之后（或拆到独立节点）。**

**恢复机制**

`interrupt()` 暂停时保存图状态并等待外部输入；恢复方式是再次调用图并传入 `Command(resume=...)`，其值成为节点内 `interrupt()` 的返回值 [1]。但节点不是从调用点续跑，而是**从头重新执行**，因此 `interrupt()` 之前的代码（含外部写入）每次恢复都会重放 [1]。文档还警告单个节点内 `while True` + `interrupt()` 循环会让每次恢复重放此前所有迭代，造成循环体代码指数级重复执行 [1]。

**重复副作用如何处理**

文档明确要求：`interrupt()` 之前的副作用“应当（理想上）幂等”，即同一操作执行多次不改变首次执行后的结果；举例是节点内更新记录的 API 调用，若 `interrupt()` 在其后，恢复时会多次重跑，可能覆盖原更新或产生重复记录 [1]。给出的做法是：在 `interrupt()` 前使用幂等操作、把副作用放到 `interrupt()` 之后、尽量把副作用拆到独立节点 [1]；并明确禁止在 `interrupt()` 前执行非幂等操作、禁止不检查是否存在就新建记录 [1]。

**限制与未覆盖之处**

- 文档未提供自动去重或幂等机制，这部分需使用者自行保证 [1]。
- 检查点持久化模式（`exit`/`async`/`sync`）影响中间状态是否保存及崩溃恢复能力，但不改变恢复时从头重跑的行为；`exit` 模式下中间状态不保存，无法从进程崩溃中恢复 [2]。
- 恢复依赖 `thread_id` 作为检查点主键，没有它无法在中断后保存状态或恢复执行 [2]。
- 中断异常不进入错误处理器与重试策略，图按常规暂停 [3]；这不改变上述重跑语义。

**取舍**

幂等写入适合无法移动位置的外部调用（如必须先行校验的更新）；把副作用后移或拆节点可彻底避免重放，但会改变执行顺序与失败语义，需按业务确认。以上均为文档明示内容，未涉及具体去重实现细节。

## Sources

1. Interrupts — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/interrupts.mdx
2. Checkpointers — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/checkpointers.mdx
3. Fault tolerance — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/fault-tolerance.mdx
