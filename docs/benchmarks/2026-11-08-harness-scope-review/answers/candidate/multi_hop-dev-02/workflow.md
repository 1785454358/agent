# multi_hop-dev-02 / workflow

Using only the frozen documentation, a node writes to an external service before interrupt(). How should resumption and duplicate side effects be handled?

Status: completed; answered: True; reason: None; model calls: 10; tools: 24; seconds: 60.412.

**结论：恢复时该节点会从头重跑，`interrupt()` 之前写外部服务的代码会再次执行，因此可能产生重复副作用。冻结文档只给出方向性要求——`interrupt` 之前的副作用应（理想上）幂等——并未给出幂等键、去重、事务等具体方案，具体保证需应用层自行落实 [1]。

**恢复起点**

`interrupt` 的工作方式是重新运行调用它的节点，所以恢复时节点从头重跑，`interrupt()` 之前已执行的代码会再次执行 [1]。恢复动作是用携带 resume 值的 `Command` 再次调用图，该值成为节点内 `interrupt()` 的返回值 [1]。

注意粒度：检查点在每个 super-step 边界创建，只能从检查点（即 super-step 边界）恢复 [2]；但同一 super-step 内已成功节点的写入已在节点（任务）级持久化，恢复时不会重跑这些成功节点 [2]。也就是说，重跑的是被中断的那个节点本身，而非整个 super-step。

**重复副作用**

文档明确以示例说明：在 `interrupt()` 之前创建新记录或向数组追加历史，会在每次恢复时产生重复记录/重复条目 [1]。文档给出的做法是：

- 在 `interrupt` 前使用幂等操作；
- 把副作用放到 `interrupt` 调用之后；
- 尽可能把副作用拆到独立节点 [1]。

文档还警告不要在单个节点内用 `while True` + `interrupt()` 循环，因为每次恢复都从头重跑，会重放此前所有迭代，导致循环体内代码指数级重复执行 [1]。

**文档未覆盖的部分**

幂等键、去重表、事务、人工核对等具体去重机制，本次可见材料均未涉及，属文档未覆盖、需应用层自行保证的部分。补偿方面，文档仅提到错误处理器可返回 `Command` 以更新状态并路由到特定节点，从而支持 Saga/补偿模式 [3]；但 `interrupt()` 在节点内抛出时不路由到错误处理器，而是通过 `GraphBubbleUp` 暂停执行，绕过重试策略和错误处理器 [3]，因此不能指望错误处理器兜住中断前的重复写入。

**适用条件与限制**

- 检查点以 `thread_id` 为主键；没有 `thread_id`，检查点无法保存状态或在 `interrupt` 之后恢复执行 [2]。
- 持久化模式影响耐久性：`"exit"` 只在执行退出时持久化，无法从执行中途的进程崩溃恢复；`"async"` 在进程崩溃时有小概率未写入检查点；`"sync"` 在下一步开始前同步写入，耐久性最高但有一定性能开销 [2]。

**实践取舍**

最稳妥的顺序是把外部写入移到 `interrupt()` 之后（拿到批准再写），或拆成独立节点；若业务上必须在中断前写，则需应用层自行实现幂等/去重，因为文档只要求“应幂等”而未提供机制 [1]。

## Sources

1. Interrupts — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/interrupts.mdx
2. Checkpointers — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/checkpointers.mdx
3. Fault tolerance — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/fault-tolerance.mdx
