# multi_hop-dev-02

Using only the frozen documentation, a node writes to an external service before interrupt(). How should resumption and duplicate side effects be handled?

Component status: completed; error: None; new Provider calls: 1.

节点在 interrupt() 之前写入外部服务时，恢复执行会重跑该节点，因此该副作用应设计为幂等，否则可能重复写入或覆盖原记录[1]。文档建议：在 interrupt() 前使用幂等操作、把副作用放到 interrupt() 之后、或尽量把副作用拆到独立节点[1]。恢复时用带 resume 值的 Command 重新调用图，该值成为 interrupt() 的返回值，节点从开头重跑[1]。此外，interrupt() 不进入错误处理器，也不受重试策略影响，图会正常暂停[2]。检查点按 super-step 边界创建，并在节点（任务）级持久化已完成节点的写入；同一 super-step 中其他节点失败时，成功节点的写入已持久化，恢复时不会重跑这些成功节点[3]。thread_id 是保存状态和 interrupt 后恢复执行所必需的[3]。

Unresolved gaps: []
