# multi_hop-dev-02 / multi_agent

Using only the frozen documentation, a node writes to an external service before interrupt(). How should resumption and duplicate side effects be handled?

Status: completed; answered flag: True; response reason: None; model calls: 6; seconds: 29.338.

**结论：恢复时节点会从头重跑，`interrupt()` 之前对外部服务的写入会被再次执行；因此该写入必须（理想上）幂等，否则会产生重复记录或覆盖初始更新。冻结文档只给出幂等性与放置位置建议，未规定幂等键、去重、检查点/事务或补偿机制。**

**恢复行为**

`interrupt()` 通过抛出异常暂停执行，运行时保存状态并等待外部输入 [1]；恢复时用 `Command(resume=...)` 重新调用图，恢复值成为 `interrupt()` 的返回值 [1]。关键在于：节点在每次恢复时从头重新执行 [1]，所以 `interrupt()` 之前的代码（包括外部写入）每次恢复都会重跑 [1]。文档还警告，单个节点内 `while True` + `interrupt()` 循环会因每次恢复重放全部迭代而导致指数级重执行 [1]。

**重复副作用的处理**

文档明确要求：`interrupt()` 之前调用的副作用应（理想上）幂等，即同一操作多次应用不改变初始执行之外的结果 [1]。若在写入外部记录后调用 `interrupt()`，恢复时该调用会多次重跑，可能覆盖初始更新或产生重复记录 [1]。文档给出的做法是：

- 在 `interrupt()` 前使用幂等操作（如 upsert）[1]；
- 把副作用放在 `interrupt()` 之后 [1]；
- 尽可能把副作用拆到独立节点 [1]；
- 不要执行非幂等操作，不要在未检查记录是否存在时新建记录 [1]。

**文档未覆盖的部分**

冻结文档未规定针对 `interrupt()` 前外部副作用的幂等键、去重、检查点/事务或补偿机制，仅给出上述幂等性与放置位置建议 [1]。因此这些机制属于文档未规定事项，不能作为原文要求陈述。

**适用条件与取舍**

若外部写入本身可幂等（如 upsert、按业务键覆盖），放在 `interrupt()` 前在恢复重跑下仍安全 [1]；若写入不可幂等（如插入新记录），应移到 `interrupt()` 之后或拆到独立节点，以避免恢复时重复执行 [1]。这是文档建议的放置策略，不是对幂等键或事务机制的强制规定 [1]。

## Sources

1. Interrupts — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/interrupts.mdx
