# multi_hop-dev-02

Using only the frozen documentation, a node writes to an external service before interrupt(). How should resumption and duplicate side effects be handled?

Component status: completed; error: None; new Provider calls: 1.

节点在 interrupt() 之前调用外部服务时，恢复执行会从节点开头重新运行该节点，因此 interrupt() 之前的外部写入会被再次执行，可能覆盖首次更新或产生重复记录[1]。文档要求：interrupt() 之前的副作用应（理想情况下）具备幂等性，即同一操作执行多次不改变首次执行后的结果[1]；推荐做法是使用幂等操作、把副作用放在 interrupt() 之后，或在可能时把副作用拆分到单独节点[1]。此外，interrupt() 在节点内抛出时不会被路由到错误处理器，也不经过重试策略，图按常规暂停[2]；恢复时通过携带 resume 值的 Command 再次调用图，该值成为 interrupt() 调用的返回值[1]。检查点按 super-step 边界创建，并在节点（任务）级持久化写入，同一 super-step 中已成功节点的写入在恢复时不会重跑[3]；但该机制针对节点完成后的写入，不能替代上述对 interrupt() 之前副作用的幂等要求。

Unresolved gaps: []
