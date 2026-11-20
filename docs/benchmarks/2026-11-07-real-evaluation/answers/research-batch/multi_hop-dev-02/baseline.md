# multi_hop-dev-02 / baseline

Using only the frozen documentation, a node writes to an external service before interrupt(). How should resumption and duplicate side effects be handled?

Status: completed; answered flag: True; response reason: None; model calls: 2; seconds: 11.244.

**结论：恢复时整个节点会从头重跑，`interrupt()` 之前的外部写入会再次执行，因此该写入必须幂等，或移到 `interrupt()` 之后/独立节点中。**

恢复机制：`interrupt()` 通过抛出异常暂停执行，运行时保存状态并等待外部输入；恢复时运行时**从节点开头重启整个节点**，而不是从 `interrupt()` 那一行继续，所以 `interrupt()` 之前已运行的代码会再执行一遍 [1]。恢复方式是再次调用图并传入 `Command(resume=...)`，该值是 `interrupt()` 调用的返回值 [1]；文档明确 `Command(resume=...)` 是唯一可用于 `invoke()`/`stream()` 输入的 `Command` 模式 [1]。

重复副作用：正因为节点重跑，`interrupt()` 前的副作用会被多次执行，可能覆盖首次更新或产生重复记录 [1]。文档要求这类副作用“理想上”幂等，即同一操作执行多次不改变首次执行后的结果 [1]。

可采用的三种做法 [1]：

| 做法 | 效果 |
|---|---|
| 在 `interrupt()` 前使用幂等操作（如 upsert） | 重跑结果一致 |
| 把副作用放到 `interrupt()` 之后 | 仅在拿到批准后执行一次 |
| 把副作用拆到独立节点 | 在批准后的节点中只执行一次 |

文档同时列出禁止项：不要在 `interrupt()` 前执行非幂等操作，不要在不检查记录是否已存在的情况下创建新记录 [1]。另需注意，`interrupt()` 不会被路由到错误处理器，也不走重试策略，图照常暂停 [2]；这与“重跑节点”的恢复语义是两件事，不能靠错误处理器去补偿重复写入。

若外部服务本身不支持幂等键，文档未给出补偿或去重机制，只能按上述“后移或拆分”规避；这是依据 [1] 的取舍，不是原文承诺的额外能力。

## Sources

1. Interrupts — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/interrupts.mdx
2. Fault tolerance — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/fault-tolerance.mdx
