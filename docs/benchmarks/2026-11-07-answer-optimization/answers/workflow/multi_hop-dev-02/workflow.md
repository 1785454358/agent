# multi_hop-dev-02 / workflow

Using only the frozen documentation, a node writes to an external service before interrupt(). How should resumption and duplicate side effects be handled?

Status: completed; answered: True; reason: None; model calls: 8; seconds: 40.841.

**结论：恢复时节点会从头重跑，`interrupt()` 之前的外部写入会被再次执行；冻结文档要求这类副作用（理想情况下）幂等，且幂等责任在节点代码层，文档未称框架会自动去重。**

**恢复语义**

- `interrupt()` 通过重跑调用它的节点来实现；恢复时节点从头重新执行，而不是从 `interrupt` 点继续 [1]。
- 恢复方式是再次调用图并传入含 resume 值的 `Command`，该值成为节点内 `interrupt()` 的返回值，节点继续执行；但节点本身仍从头重跑 [1]。
- 因此 `interrupt()` 之前对外部服务的写入，在恢复时会被再次执行 [1]。

**重复副作用处理**

- 文档明确：`interrupt` 之前调用的副作用应当（理想情况下）是幂等的；幂等指同一操作可多次应用而不改变初始执行之外的结果 [1]。
- 文档举例：节点内先调用 API 更新记录、再 `interrupt()`，恢复时该调用会重跑多次，可能覆盖初始更新或产生重复记录 [1]。
- 文档给出的做法：在 `interrupt()` 前使用幂等操作、把副作用放到 `interrupt()` 之后、尽量把副作用拆到独立节点 [1]；并明确不要执行非幂等操作、不要在不检查记录是否已存在的情况下新建记录 [1]。
- 文档警告：不要在单个节点内用 `while True` + `interrupt()` 循环，因为每次恢复都从头重跑，循环中多次 `interrupt()` 会导致每次恢复重放此前所有迭代，产生指数级重复执行 [1]。

**边界**

- 上述幂等要求是文档对调用方/节点代码的建议，文档没有说明框架层会自动去重或提供事务性保证 [1]。
- 检查点机制（`thread_id`、super-step 边界检查点）用于保存状态和恢复执行 [2]，但本次可见材料未说明它能消除 `interrupt` 前外部写入的重复执行。
- 故障容错文档中的重试会清除超时尝试的写入 [3]，但那是超时/重试路径，不是 `interrupt` 恢复路径，不能据此推断 `interrupt` 场景已有去重。

**实践取舍**：若外部写入无法幂等，应把它移到 `interrupt()` 之后或拆到独立节点 [1]；若必须放在之前，则需在节点代码内做存在性检查或去重键 [1]。

## Sources

1. Interrupts — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/interrupts.mdx
2. Checkpointers — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/checkpointers.mdx
3. Fault tolerance — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/fault-tolerance.mdx
