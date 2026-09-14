# Harness 核心机制

这一篇集中解释 Harness 中最容易被追问的边界。配合 [Harness 总体架构](02-Harness总体架构.md) 中的所有权图、工具管道和恢复时间线阅读。

## State 与 Runtime Context

State 保存会影响后续路由并需要恢复的业务事实。ConversationState 保存同一 thread 的消息、摘要、Evidence ID、Finding 和缺口，TurnState 保存当前 run 的输入、意图、策略和结果。计划与任务进度属于工作记忆，也进入策略自己的 State。

Runtime Context 保存模型客户端、Tool Gateway、Evidence Store、Memory Store、事件接口和时钟。这些对象由组合根创建，不能稳定序列化，也不代表业务进度，因此不写入 Checkpoint。

## Tool Gateway、Evidence 与预算

所有策略只能通过 Tool Gateway 访问网络工具。Gateway 先检查工具注册、调用者权限、参数模型和 URL 来源，再查询执行账本。只有新的合法调用才会预留 Agent、Mode、Run 三层预算。

缓存复用相同数据输入，Singleflight 合并同一时刻的相同请求，Execution Ledger 记录同一逻辑 call_id。三者解决的问题和生命周期不同。

网页正文由 Evidence Store 管理规范 URL、内容哈希、分块和版本。State、ToolResult 和长期记忆只保存 Evidence ID 或受限预览，避免 Checkpoint 和模型上下文不断膨胀。

## Checkpoint、Ledger 与恢复

Checkpoint 保存图状态和下一执行位置。Execution Ledger 保存工具调用身份、所有权、结果和预算消耗。节点在 Provider 成功后、下一个 Checkpoint 前崩溃时，恢复会重放节点，稳定 call_id 可以让 Ledger 返回已经提交的结果。

恢复后的新 BudgetManager 会在第一次预留前读取 Ledger 消耗量，并重建 Agent、Mode、Run 三层计数。这个设计防止 Worker 重启后额度清零。Ledger 读取失败时当前实现会记录异常并 fail-open，这是一项可用性优先的取舍，也意味着预算保护在该故障下会减弱。

## MySQL、Redis 与租约

MySQL 保存运行、事件、Checkpoint、Evidence、Memory、租约和工具账本，是分布式模式的权威事实来源。Chroma 只保存长期记忆的向量索引。Redis Streams 投递任务，取消键传递取消信号，Pub/Sub 唤醒 SSE。最终状态写入 MySQL 后，Worker 才 ACK 消息。

run lease 防止两个 Worker 执行同一个 run，thread lease 防止同一会话同时启动两个 Turn。Worker 心跳会续期两种租约。任务采用 at-least-once 投递，Provider 成功但 Ledger 尚未提交的窗口仍可能重复调用。外部写操作还需要 Provider 幂等键或补偿。

## 响应与引用

研究策略决定怎样取得证据，响应模式决定怎样表达证据。默认 Answer 控制阅读成本，明确要求报告后才进入 Report。响应子图只加载允许的 Evidence，并在生成后校验引用编号。没有可信引用时返回 partial 降级结果。

## 记忆设计完整回答

### 工作记忆

工作记忆是任务的可恢复执行事实，包括计划、已完成任务、查询结果、Finding、Evidence ID、未解决缺口和结束原因。它影响后续路由，因此进入策略 State 或顶层 State。

### 短期会话记忆

近期原始消息和结构化 `ConversationSummary` 保存在 `ConversationState`。当前按消息条数控制窗口，软上限 24，硬上限 60。超出窗口的旧消息由 summarizer 压缩为主题、用户约束、已确认事实、实体、未解决问题和历史结论。摘要字段还有数量上限，防止多轮压缩后无限增长。

当前触发条件按消息数量实现，还没有按真实 Token 精确计算。Token 感知压缩属于下一步优化。

### 长期记忆

长期记忆跨 thread 或 session 复用。当前主要落地两类内容。

- Preference 保存用户明确要求记住的稳定偏好。
- Fact 保存研究整理出的可信事实，写入时必须绑定 Evidence ID。

系统不会把所有聊天直接存入长期记忆。聊天包含临时要求、错误信息、过时结论和敏感内容，全量保存会提高召回噪声、成本与隐私风险。

Distributed 召回时，MySQL 先按 namespace、memory_type、status 和 expires_at 过滤候选。BGE-M3 生成查询向量，Chroma 只在 candidate_ids 内执行 TopK。命中 ID 必须回查 MySQL，最终排序再加入 importance、confidence 与 recency。Local 使用进程内 Memory Store 完成同样的候选过滤与回查，结构化记忆不会跨 API 重启。Chroma 不拥有权威数据，写入或查询失败时不会破坏权威 Store 中的记忆，系统会尝试修复索引或降级到关键词排序。

### 六个生命周期问题

| 问题 | 当前实现 |
| --- | --- |
| 何时存 | 用户明确要求记住，或研究结束后整理有来源的 Finding |
| 存什么 | 稳定偏好、有 Evidence 支持的事实，不存完整聊天、正文和隐藏推理 |
| 如何组织 | `("user", user_id, "preferences")` 与 `("workspace", workspace_id, "facts")` |
| 何时召回 | Research、Incremental Research、Report Request 等需要历史信息的意图，先结构化过滤再语义 TopK |
| 如何更新 | 相同 namespace/type/subject 身份下，同内容幂等复用，内容变化生成新版本并 supersedes 旧版本；语义相近但 subject 不同的记录暂不自动合并 |
| 如何遗忘 | expires、stale、逻辑删除和物理删除，自动清扫尚待接入 |

当前 API 组合根注入固定的 `local-user` 与 `local-workspace`，所以部署仍是单租户。数据结构预留了 namespace，真正的多租户隔离需要先接入认证身份。

[返回阅读目录](00-阅读目录.md)
