# multi_hop-dev-02

Using only the frozen documentation, a node writes to an external service before interrupt(). How should resumption and duplicate side effects be handled?

Component status: partial; error: None; new Provider calls: 1.

结论：节点在 `interrupt()` 之前写外部服务时，恢复会重跑该节点，因此该外部写入必须幂等，否则可能重复写入或覆盖原记录；更稳妥的是把副作用放到 `interrupt()` 之后，或拆到独立节点。[1]

依据与做法：
1. 恢复机制：`interrupt()` 通过抛出异常暂停执行，运行时保存状态并等待外部输入；恢复时用带 resume 值的 `Command` 再次调用图，该值成为 `interrupt()` 的返回值。[1] 由于中断靠重跑调用它的节点实现，`interrupt()` 之前的副作用会被再次执行。[1]
2. 重复副作用：原文明确要求 `interrupt()` 之前调用的副作用“理想上”应幂等；幂等指同一操作执行多次不改变初次执行后的结果。示例是节点内先调用 API 更新记录、再 `interrupt()`，恢复时该调用会重跑多次，可能覆盖初次更新或产生重复记录。[1]
3. 推荐顺序与边界：✅ 在 `interrupt()` 前使用幂等操作；✅ 把副作用放在 `interrupt()` 调用之后；✅ 尽可能把副作用拆到独立节点。[1]
4. 恢复前提：checkpointer 以 `thread_id` 为主键；没有它，checkpointer 无法保存状态，也无法在 `interrupt` 后恢复执行。[2] 恢复只能从检查点（即 super-step 边界）继续。[2]
5. 已完成节点的写入：同一 super-step 中某节点失败时，其他已成功节点的 pending writes 已持久化，恢复时不会重跑这些成功节点。[2] 但本情形是同一节点在 `interrupt()` 前已产生外部副作用，仍受上述重跑规则约束。[1]
6. 中断与错误处理：节点内 `interrupt()` 不会进入 error handler，也不走重试策略，图按常规暂停。[3] 因此不能指望错误处理器去补偿该外部写入。[3]
7. 持久化模式影响：`"exit"` 只在成功、出错或人工中断退出时持久化，进程崩溃中途无法恢复；`"async"` 在进程崩溃时存在未写检查点的小风险；`"sync"` 在下一步开始前同步写入，持久性高。[2] 若需在中断/崩溃后可靠恢复，应结合该模式评估。[2]

可见材料没有给出针对外部服务去重键、事务或补偿接口的具体实现规范，不能据此量化重复次数或保证 exactly-once。[1]

Unresolved gaps: ["外部服务应使用何种幂等键或去重机制，材料未给出具体规范。", "如何在该场景下实现 exactly-once 或可验证的补偿，材料无依据。"]
