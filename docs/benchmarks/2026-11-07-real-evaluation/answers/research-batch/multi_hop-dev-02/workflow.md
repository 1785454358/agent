# multi_hop-dev-02 / workflow

Using only the frozen documentation, a node writes to an external service before interrupt(). How should resumption and duplicate side effects be handled?

Status: completed; answered flag: True; response reason: None; model calls: 6; seconds: 29.672.

**结论：** 冻结文档说明，`interrupt()` 通过重新运行调用它的节点来恢复执行，因此 `interrupt()` 之前的外部写入在恢复时会被再次执行；文档要求这类副作用“理想上”幂等，并建议把副作用放到 `interrupt()` 之后或拆到独立节点。文档未承诺框架会自动去重或保证外部写入只执行一次 [1]。

**恢复语义（r1）**

`interrupt()` 在节点内抛出异常使运行时暂停并保存状态；恢复时用 `Command` 重新调用图，恢复值成为 `interrupt()` 的返回值，节点继续执行 [1]。关键后果是：节点不是从 `interrupt()` 处“续跑”，而是整个节点重跑，`interrupt()` 之前的代码会再次执行 [1]。

**重复副作用（r2）**

文档明确警告：若在外部 API 调用之后才调用 `interrupt()`，恢复时该调用会被多次重跑，可能覆盖初始更新或产生重复记录 [1]。给出的处理方式有三条 [1]：

- 在 `interrupt()` 前使用幂等操作（如 upsert，而非无条件新建记录）；
- 把副作用放在 `interrupt()` 之后；
- 尽可能把副作用拆分到独立节点。

文档同时列出反例：不要在 `interrupt()` 前执行非幂等操作，不要不检查记录是否存在就新建记录 [1]。

**责任边界（r3）**

文档以建议性措辞（“should (ideally) be idempotent”）把 `interrupt()` 前副作用的幂等性交由调用方负责，并给出放置位置与拆分节点的实践建议；文档未声明框架会自动去重或保证外部写入只执行一次 [1]。

**缺口说明：** 本次可见材料未给出框架层面的去重机制、事务性外部写入保证或补偿接口的具体调用方式；上述结论仅基于当前可见的 Interrupts 文档 [1]，不能推出全部文档均无相关说明。

## Sources

1. Interrupts — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/interrupts.mdx
