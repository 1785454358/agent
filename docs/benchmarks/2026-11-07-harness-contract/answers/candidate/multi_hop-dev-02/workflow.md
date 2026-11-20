# multi_hop-dev-02 / workflow

Using only the frozen documentation, a node writes to an external service before interrupt(). How should resumption and duplicate side effects be handled?

Status: completed; answered: True; reason: None; model calls: 6; tools: 14; seconds: 29.754.

结论：按冻结文档，恢复时用同一线程再次调用图并传入 `Command` 的 resume 值，该值成为节点内 `interrupt()` 的返回值，节点从该处继续 [1]。但“外部写入在 interrupt 之前”这一情形，文档明确要求该副作用**幂等**，因为中断恢复会重跑调用它的节点 [1]。

条件与取舍：

- 恢复机制：中断暂停执行并保存图状态；恢复时 `Command(resume=...)` 回传给 `interrupt()`，节点继续 [1]。每次恢复中节点代码只运行一次、`interrupt()` 只调用一次后退出 [1]。
- 重复副作用：文档指出，由于中断通过重跑所在节点实现，`interrupt` 之前的副作用应（理想上）幂等；否则恢复时可能重复执行，造成覆盖原更新或创建重复记录 [1]。建议把副作用放在 `interrupt` 之后，或拆到独立节点 [1]；不要执行非幂等操作，也不要在未检查存在性时新建记录 [1]。
- 检查点边界：检查点在 super-step 边界创建，并按节点（任务）级持久化写入；同一 super-step 中某节点失败时，已完成节点的写入已持久化，恢复时不重跑这些成功节点 [2]。这能避免“同一步内其他成功节点”的重复执行，但**不能**推出“同一节点内 interrupt 之前的写入不会重跑”——文档恰恰要求该写入幂等 [1]。

因此，处理方式应是：恢复用 `Command(resume=...)` 续跑；对 interrupt 前的外部写入做幂等设计（如按业务键 upsert/去重），或移到 interrupt 之后/独立节点。文档未给出针对外部服务的通用去重实现细节，需按具体服务自行保证幂等。

## Sources

1. Interrupts — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/interrupts.mdx
2. Checkpointers — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/checkpointers.mdx
