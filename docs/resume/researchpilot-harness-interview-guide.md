# 多模式深度研究 Agent 面试指南

这份材料按项目最终形态准备。讲解时始终以 Agent Harness 为主线。Workflow、Plan-and-Execute 和 Multi-Agent 是三种 Research Profile，负责决定怎样研究。Answer、Brief 和 Report 是三种响应路径，负责决定怎样表达结果。研究深度与输出形式彼此独立。

## 90 秒项目介绍

我做的是一个面向复杂开放问题的多模式深度研究 Agent。它支持原文查证和连续追问，默认给简洁答案，用户明确提出时才生成报告。

项目以 LangGraph Agent Harness 为组织中心。HarnessGraph 统一处理意图、上下文、研究路由、响应、记忆和恢复。具体研究由三个 Profile 子图完成。Workflow 走固定流程，Plan-and-Execute 按证据缺口调整计划，Multi-Agent 由 Supervisor 并发调度 Researcher。父图只接收统一结果，三个子图保留各自状态。

工具侧调用统一经过 Tool Gateway，正文由 Evidence Store 管理，图状态只保存 Evidence ID。短期记忆采用滑动窗口和结构化压缩，长期记忆覆盖写入、召回、更新与遗忘。社区 Checkpointer 把状态保存到 MySQL，Redis Streams 负责投递与唤醒。三种策略因此共享同一套可恢复、可追踪的运行规则。

## 3 分钟项目介绍

我做的是一个多模式深度研究 Agent，处理需要检索、阅读原文、交叉查证和连续追问的问题。系统把研究策略与输出形式分开。Research Profile 决定怎样查，Response Graph 决定怎样表达。用户默认得到简洁答案，明确要求时才生成报告。

项目以 LangGraph Agent Harness 为组织中心。HarnessGraph 管理一轮请求，识别追问、增量研究、Profile 切换和报告请求，再装配近期消息、结构化摘要与已有 Evidence。确实需要跨会话信息时才召回长期记忆。

三个研究 Profile 都是子图。Workflow 走固定检索流程。Plan-and-Execute 把计划、执行、评估和重规划写入 State。Multi-Agent 由 Supervisor 拆分任务并并发运行 Researcher。父图只接收统一 ResearchOutcome，子图私有状态不会进入主图。Writer 只属于 Response Graph。

工具侧调用统一走 Tool Gateway，模型调用走 ModelGateway。网关检查权限、参数、幂等和预算，并控制超时。Provider SDK 的内置重试关闭，临时异常交给 LangGraph Node RetryPolicy 重放工具节点。Evidence Store 唯一保存规范化、分块且有大小上限的正文记录，Graph State 和长期记忆都只保留 Evidence 引用。

短期记忆采用滑动窗口与结构化动态压缩。长期记忆保存 Preference、Fact 和 Episode，按作用域筛选候选，再用本地 BGE-M3 做语义重排。MySQL 保存权威状态，社区 MySQL 适配器只提供 Checkpointer。长期记忆由项目自己的 MySQL Memory Store 管理。Redis Streams 只负责投递和唤醒。

系统采用 at-least-once。账本只复用已提交的成功结果。Provider 成功但账本未提交时仍可能重复请求，写操作依靠 Provider 幂等键或补偿，只读搜索能容忍重复但可能增加费用。我再用同一问题集比较三个 Profile，为 Auto 提供评测基线。

## 一次请求怎样经过 Harness

以下流程以用户在已有会话中提出追问为例。

1. 接口层接收 `thread_id`、当前输入、显式 Profile 选择和可选的响应偏好，并生成本轮 `run_id`。同一 thread 同时只允许一个会修改会话状态的 active run 持有 MySQL Lease，后续请求排队串行执行，避免两个 run 覆盖同一份 Conversation State。
2. HarnessGraph 规范化请求，识别普通对话、澄清、研究、增量研究、切换 Profile、报告请求或记忆更新等意图。
3. 系统重置上一轮的临时 Turn State，同时从 Checkpoint 恢复 Conversation State。短期上下文由结构化摘要、最近消息、已确认 Finding、未解决问题和 Evidence ID 组成。
4. Memory Router 根据意图决定是否访问长期记忆。普通追问优先使用短期状态。新会话、增量研究、报告生成或明确的证据缺口才触发自动召回。Profile 执行中也可以用 `search_memory` 查询具体缺口。
5. Research Router 决定是否需要研究。已有证据足够时可以跳过 Research Profile。需要补查时，Profile Registry 解析 Workflow、Plan-and-Execute 或 Multi-Agent，并把统一 ResearchInput 交给对应子图。
6. Profile 子图只管理自己的研究状态。它通过 Runtime Context 获取 ModelGateway、Tool Gateway、Evidence Store、事件接口和时钟，不把数据库连接或客户端放进可序列化 State。模型调用进入 ModelGateway，工具侧调用进入 Tool Gateway。
7. 每个工具侧调用进入 Tool Gateway。网关先校验权限和参数，再处理安全、幂等、预算、缓存与超时，并让临时异常继续向上抛出。Provider SDK 的内置重试设为 0，只有 LangGraph Node RetryPolicy 重放当前工具节点。超时只能停止本地等待，无法保证远端请求已经取消。工具返回受控预览和 `data_ref`，不会把整页正文塞回模型消息。
8. Evidence Store 对抓取正文做规范化、分块、单块与总量上限控制，并保存内容哈希和元数据。Profile 根据 Evidence 形成 Finding、证据引用和未解决缺口，最后只通过 ResearchOutcome 把这些结果交回 HarnessGraph。
9. Response Router 独立选择 Answer、Brief 或 Report。这个选择不会改变研究 Profile。所有 Writer 节点都属于 Answer、Brief 或 Report Response Graph。Multi-Agent Profile 只负责研究和聚合 ResearchOutcome，不包含 Writer。Answer 和 Brief 默认使用已有 Evidence，Report 先检查覆盖范围，用户新增研究范围时才重新进入当前 Research Profile。
10. 输出完成后，Memory Consolidation 更新滑动窗口和结构化摘要，并筛选长期记忆候选。未通过来源、稳定性或敏感性检查的内容不会写入长期记忆。
11. LangGraph 在节点边界保存 Checkpoint。事件接口持续记录节点、模型、工具、预算和终止原因，供 SSE 展示和故障排查。运行最终进入 completed、partial、failed 或 cancelled。

## Harness 模块边界

| 模块 | 负责什么 | 主要输入 | 主要输出 | 失败边界 |
| --- | --- | --- | --- | --- |
| HarnessGraph | 编排单轮请求生命周期，连接路由、研究、响应、记忆和持久化 | Conversation State、Turn State、RunnableConfig、Runtime Context | 更新后的会话状态、响应和终态 | 输入或权威存储无效时停止运行。Profile 的业务失败被规范化为 partial 或 failed，不让异常状态直接泄漏到接口层 |
| Profile Registry | 注册并解析可用 Research Profile，保证统一输入输出契约 | 强类型 Profile 标识、Profile 子图注册信息 | 目标子图或明确的未注册错误 | 不接受旧名称和任意字符串，不在注册表内部偷偷兼容历史路由 |
| Runtime Context | 注入不可序列化的运行依赖 | user、workspace、模型网关、工具网关、存储、事件接口和时钟 | Graph 节点可访问的运行资源 | 依赖缺失在节点入口失败，不把客户端、连接或锁写入 Checkpoint |
| State | 保存可序列化、可恢复的会话与本轮业务状态 | 节点更新、Reducer 合并结果 | Conversation State、Turn State、ResearchOutcome 引用 | State 校验拒绝未知或不兼容字段。大型正文和进程内对象不得进入 State |
| Tool Gateway | 统一管理工具侧调用和副作用 | 工具名、规范化参数、调用身份、Profile 权限和预算 | 受控 ToolResult、Evidence 引用、执行账本及事件 | Gateway 负责错误分类、超时和幂等，并让临时异常上抛。Provider SDK 重试设为 0，只有 LangGraph Node RetryPolicy 重放节点。超时不保证远端取消 |
| Evidence Store | 唯一管理规范化、分块且有大小上限的正文记录 | 搜索候选、网页正文、来源元数据和内容哈希 | Evidence ID、版本、受控片段和有效性状态 | 入库或权威存储失败时不得生成无来源引用，失效证据不进入回答上下文 |
| Memory 子系统 | 管理短期上下文装配和长期记忆生命周期，不复制 Evidence 正文 | 会话消息、摘要、Evidence 引用、意图和记忆候选 | 上下文包、召回结果、摘要更新和版本化 Preference、Fact、Episode | 作用域不匹配、来源不足或敏感内容会被拒绝。召回结果只作为候选上下文，不直接当成事实 |
| Checkpointer | 在节点边界持久化 Graph State，支持按 thread 恢复 | thread、checkpoint、序列化状态和节点写入 | 可恢复快照、版本和 pending writes | Checkpoint 写入失败时停止推进，避免业务状态与执行位置分叉 |
| Observability | 记录用户事件、开发 Trace、Metric 和结构化 Log | thread、run、attempt、Profile、节点、Agent、工具和终止信息 | SSE 事件、调用链、聚合指标和诊断日志 | 观测失败不能伪造成功记录。关键审计事件无法持久化时按配置中止高风险操作 |

## Harness 深挖回答

### Harness 和普通 Agent 封装有什么区别

我的理解里，普通 Agent 封装通常解决一次模型调用怎么接工具，关注的是 Prompt、Function Calling 和返回结果。Harness 管理的是一次 Agent 执行从进入到结束的运行协议。它规定状态怎样保存，依赖怎样注入，Profile 怎样接入，工具副作用怎样治理，失败后从哪里恢复，事件怎样关联到同一个 run。

在这个项目里，HarnessGraph 只负责编排公共生命周期，具体研究交给 Profile 子图。这样新增 Profile 时，它只需要实现统一 ResearchInput 和 ResearchOutcome，不需要重新实现记忆、预算、工具权限、Checkpoint 和可观测性。目前业界没有一套统一的官方 Harness 标准。我在项目里把它定义为一组明确、可测试的工程边界。

### 为什么三种编排都使用 LangGraph

三种 Profile 都有状态变化、条件分支和失败恢复，只是自主程度不同。Workflow 的路径固定，也适合用图表达，因为并行搜索、证据聚合和 Checkpoint 边界仍然清楚。Plan-and-Execute 的计划循环如果写成 Python `while`，循环中的计划、执行结果和重规划次数很难统一持久化。Multi-Agent 的并发派发和局部失败也需要显式状态。

统一使用 LangGraph 后，循环、条件边、并发和 interrupt 都遵循同一套执行模型。测试可以直接断言经过了哪些节点，恢复也能回到确定边界。LangGraph 负责图运行，Harness 负责定义这些图如何共享运行规则，它们处在不同层次。

### 三种 Profile 怎样共享能力又隔离状态

我给三个 Profile 设计了相同的边界。输入包含问题、会话摘要、历史 Evidence 引用、未解决缺口、预算和时间信息。输出统一为 ResearchOutcome，包含 Profile、Evidence ID、Finding、剩余缺口、执行步数和结束原因。

Harness 只理解这份公共契约。Workflow 的查询队列、Plan-and-Execute 的计划任务、Multi-Agent 的 Supervisor 和 Researcher 消息都留在各自子图中。运行依赖统一从 Runtime Context 获取，工具都经过 Tool Gateway。共享发生在能力和协议层，隔离发生在状态和决策层。

### Research Profile 和 Response Graph 为什么分开

Research Profile 决定怎样获得足够证据，Response Graph 决定怎样把已有证据表达给用户。一个用户可以选择 Multi-Agent 做深入研究，但只要一个简短答案。也可以先用 Workflow 得到材料，随后明确要求整理成正式报告。

如果把报告绑定到深度研究模式，系统会在普通追问里持续输出长报告，也很难判断报告的新范围是否需要补查。分开以后，默认走 Answer，明确要求报告才走 Report。Report 检查 Evidence 覆盖范围，发现用户增加了问题范围，再调用当前 Research Profile 补充证据。

### Tool Gateway 的处理顺序怎样设计

我的顺序是先解析工具和 Profile Allowlist，再做参数与安全校验。随后查询幂等账本，确认是否存在已经持久化的成功结果。确实需要执行时先预留预算，再检查缓存和 Singleflight，记录开始事件后在超时边界内执行一次。拿到结果后做规范化和质量校验，必要时写入 Evidence Store，最后提交或释放预算并记录完成事件。

这个顺序有几个约束。非法调用不能先消耗外部资源。并发任务要先预留额度，不能各自读取同一份剩余额度。幂等命中和缓存命中要区分，前者要求成功记录已经提交，后者说明相同输入有可复用数据。Gateway 负责错误分类、超时和幂等，然后让临时异常向上抛出。Provider SDK 的内置重试设为 0，只有 LangGraph Node RetryPolicy 重放工具节点，避免重试次数相乘。超时只能结束本地等待，远端请求仍可能继续完成，所以恢复时还要按幂等键检查账本。

ModelGateway 采用相同的重试所有权。模型 SDK 的内置重试同样关闭，临时模型异常交给对应 LangGraph 模型节点的 RetryPolicy，确保一个错误只有一个重试层级。

### Evidence 为什么在 State 里只保存引用

网页正文可能很大，直接放进 Graph State 会让每次 Checkpoint 都重复序列化，消息上下文也会迅速膨胀。Evidence Store 是正文的唯一所有者，负责规范化、分块，并限制单块大小和单条 Evidence 总量。State 和长期记忆都只保存 Evidence ID。节点需要内容时按 ID 取受控片段。

这样做还能把来源管理集中起来。Evidence 会记录规范化 URL、内容哈希、抓取时间、发布时间和有效状态。引用生成只允许使用实际装配进输出上下文的 Evidence，避免搜索摘要被误当成原文，也避免 Response Graph 引用没有进入自身上下文的来源。

### 滑动窗口和动态压缩怎样配合

滑动窗口保留最近若干轮原始消息，因为追问里的指代、用户刚刚纠正的内容和语气要求依赖原文。历史消息超过 Token 软阈值时，Context Middleware 把较早部分压缩成结构化摘要。摘要包含当前主题、用户约束、已确认事实、实体关系、未解决问题、此前结论和 Evidence 引用。

压缩是增量的。新摘要根据旧摘要和本次被移出窗口的消息生成，并经过结构化校验和长度上限检查。达到硬阈值时，大型工具观察从模型上下文移除，只保留 Evidence ID。这样近期原文负责局部连贯，结构化摘要负责长期约束，Evidence Store 负责可回溯事实。

### 长期记忆怎样覆盖完整生命周期

我会按六个问题解释长期记忆。

第一，何时存。用户明确要求记住，稳定偏好被重复确认，可信 Evidence 通过质量检查，或者研究结束后有来源支持的结论需要跨会话复用时，系统才生成候选记忆。

第二，存什么。长期记忆保存 Preference、Fact、Episode 和 Evidence 引用，并带上作用域、来源、置信度、时效状态、版本、到期时间和替代关系。Evidence 正文只由 Evidence Store 保存。临时表达、失败调用、无来源推断、敏感凭据和中间推理不保存。

第三，如何组织。记忆按 user、workspace、thread 和 global 作用域隔离，再按类型建立 namespace。默认禁止跨用户或跨 workspace 召回。Global 只保存经过策略筛选、不含私人信息的研究经验。

第四，何时召回。新会话、增量研究、报告生成和证据缺口可以触发 Harness 自动召回。普通追问优先使用短期记忆。Agent 遇到具体缺口时还能调用 `search_memory`。检索先按 namespace、所有者、状态和时间过滤，并限制候选数量，再用本地 BGE-M3 做语义评分与重排，同时考虑关键词、来源质量和置信度。向量检索不会跨越作用域边界，也不会扫描无上限候选集。

第五，如何更新。Fact、Preference 和 Episode 采用版本化追加，新记录用 `supersedes` 关联旧版本。Evidence 的重新抓取与正文版本由 Evidence Store 管理，长期记忆只更新引用。用户纠正和置信度变化都会留下审计轨迹。

第六，如何遗忘。过期、来源失效、冲突替代、长期未采用和用户删除都会改变记忆状态。系统可以先降低召回权重，再做逻辑删除。用户删除或保留策略要求彻底清除时才执行物理删除。

### Checkpoint 和幂等账本怎样配合恢复

Checkpoint 保存 Graph 在节点边界的可恢复状态，工具执行账本保存已经提交的调用结果。Worker 中断后，新 Worker 根据同一个 `thread_id` 从最近 Checkpoint 恢复。纯计算节点允许重放。模型结果如果已经作为节点结果提交，就直接复用状态。工具调用根据 run、节点、任务、工具名和规范化参数生成稳定幂等键，先查账本再决定是否执行。

只有 Checkpoint 还不够。中断可能发生在 Provider 已经成功、账本成功记录尚未提交的窗口。恢复后同一个节点会再次运行，此时账本无法证明上次调用已经完成，远端请求可能重复。支持幂等键的 Provider 可以拒绝重复写入，其他写操作需要 Outbox 配合幂等消费者，或者采用补偿与人工确认。当前搜索和抓取是只读调用，可以容忍效果重复，但仍可能增加调用费用。另一个窗口是账本成功记录已经提交、Checkpoint 尚未提交，此时恢复会命中相同幂等键并复用结果。权威存储无法提交时，运行停止，不能一边推进 Graph 一边留下不一致状态。

### 为什么选择 MySQL Checkpointer，它有哪些限制

项目已有 MySQL 技术栈，我希望业务状态、工具账本、长期记忆和 Checkpoint 由同一套权威数据库管理，减少部署依赖。LangGraph 官方提供 `BaseCheckpointSaver` 扩展接口，我使用社区维护的 `langgraph-checkpoint-mysql[asyncmy]` 适配器实现项目实际用到的核心 Checkpointer 能力。我不会宣称它与最新接口的全部行为完全一致，也不会把它称为官方内置支持。部署固定适配器版本，数据库使用 MySQL 8.0.19 及以上，并在启动阶段执行 `setup()`。

社区实现需要我承担额外验证。契约测试覆盖 State 序列化、`thread_id`、checkpoint namespace、pending writes 和项目用到的异步并发行为。升级 LangGraph 或适配器前先做兼容回归。故障注入会在 Planner 后、工具成功后、部分 Researcher 完成后和 Report Writer 节点前中断 Worker，检查恢复位置与重复调用。这个社区依赖只提供 Checkpointer，长期记忆由项目自建的 MySQL Memory Store 和 Repository 管理。如果这些验证不通过，我不会声称具备可靠恢复能力。

### Redis 和 MySQL 怎样分工

MySQL 是权威状态源，保存会话、运行记录、Checkpoint、Evidence 元数据、检索索引与正文记录、长期记忆和工具执行账本。Evidence 表由 Evidence Store 独占访问，Memory Store 只保存 Preference、Fact、Episode 和 Evidence 引用。Redis Streams 承担工作投递、消费者组、Worker 唤醒和取消通知，适合处理短暂的调度状态。

Worker 收到 Redis 消息后仍要到 MySQL 获取运行状态和租约。同一 thread 只允许一个修改状态的 active run 持有 Lease，后续 run 排队，确保 Conversation State 串行演进。Redis 消息丢失或重复都不能改变最终事实。Recovery Scanner 可以根据 MySQL 中未完成且租约过期的 run 重新投递。取消请求也先写入 MySQL，再用 Redis 加快通知。这样 Redis 可以更换或短暂故障，权威执行记录仍然存在。

### 为什么采用 at-least-once，无法承诺 exactly-once

Redis Streams 的消息在消费者确认前可能被其他 Worker 重新认领。Worker 也可能在外部调用成功后、确认消息或提交 Checkpoint 前崩溃。因此同一个 run 或节点有可能执行多次，系统只能保证任务至少会被处理一次。

项目通过 Checkpoint、租约、稳定幂等键和工具执行账本识别并降低重复影响。成功结果写入账本后可以复用。Provider 已经成功而账本尚未提交时，恢复仍可能再次请求。具备幂等键的 Provider 可以抑制重复写入，其他写操作需要 Outbox 配合幂等消费者，或者采用补偿与人工确认。搜索和抓取属于只读调用，重复不会改变远端业务状态，但可能增加费用。这个系统因此只能承诺 at-least-once，无法承诺 exactly-once。

### 怎样比较三个 Profile

我会准备固定问题集，覆盖事实检索、多约束比较、需要动态补查的问题和可并行拆分的问题。三个 Profile 使用同一模型版本、工具 Provider、预算口径和 Evidence 规则，避免配置差异掩盖策略差异。

质量侧看事实正确性、Evidence 覆盖、引用有效性、未解决缺口和任务完成度。成本侧记录模型 Token、工具次数、抓取页数和重复来源。时延侧记录总耗时、首个有效 Evidence 时间和并发利用。恢复测试再比较中断后的重复调用与最终结果。评测结果用于说明各 Profile 的适用边界，也为以后训练或设计 Auto Router 提供基线。

## 三种 Profile 的选择

| Profile | 适合的问题 | 主要优势 | 主要代价 |
| --- | --- | --- | --- |
| Workflow | 范围清楚、步骤稳定、需要快速查证的问题 | 路径短，行为容易预测，成本边界清楚 | 不会动态重规划，遇到开放缺口时适应能力有限 |
| Plan-and-Execute | 目标明确但需要分步查证、执行中可能发现新缺口的问题 | 计划和证据缺口可见，可以按评估结果调整后续步骤 | 多次规划与评估会增加模型调用和时延 |
| Multi-Agent | 可以按方向拆分、资料来源多、并行研究收益明显的问题 | Researcher 可以隔离上下文并发工作，Supervisor 统一判断覆盖范围 | 协调、聚合和重复检索的成本更高，需要更严格的预算与去重 |

三个 Profile 保持显式可选，方便用户根据深度和成本做决定，也方便在同一问题集上比较策略。Auto 暂缓，是因为自动选择需要稳定的评测标签和成本边界。没有这些基线时，Router 很可能只是在 Prompt 中做主观分类，难以解释错误选择。

## 关键取舍

### 为什么复合研究做成 Graph

搜索和抓取是原子外部能力，适合做 Tool。查询生成、并行搜索、证据评估、补查和结束判断包含自己的状态与循环，适合做 Graph。如果把整段研究包装成一个 `research_topic` 工具，Harness 只能看到一次黑盒调用，无法在内部节点保存 Checkpoint，也无法统一预算、取消和可观测性。

### 为什么大型 Evidence 不进入 Graph State

Graph State 要频繁序列化和持久化，正文进入 State 会放大 Checkpoint、数据库写入和恢复成本。Evidence Store 唯一管理规范化、分块且有大小上限的正文记录，State 与长期记忆只保存 Evidence ID。代价是节点需要一次按 ID 读取，但换来了稳定的状态体积、单一正文所有权和明确的引用边界。

### 为什么保留显式 Profile

三种 Profile 代表不同的执行语义。Workflow 强调确定路径，Plan-and-Execute 强调动态计划，Multi-Agent 强调并行分工。显式选择让预算和预期更清楚，也让评测结果能直接对应一种策略。以后加入 Auto 时，它只负责选择已经验证过的 Profile，不改变子图内部语义。

### MySQL 社区适配器带来的取舍

使用现有 MySQL 可以减少一套数据库基础设施，也能让业务状态和幂等账本保持统一事务边界。代价是 Checkpointer 来自社区实现，兼容性和升级风险需要项目自己验证。我的做法是把它放在 Infrastructure Adapter 层，Harness 只依赖 Checkpointer 协议，并用契约测试和故障恢复测试锁定行为。以后更换实现时，不需要修改三个 Research Profile。

### 记忆自动化与可控性的取舍

长期记忆完全依赖 Agent 自由调用，容易漏存，也可能把临时内容永久化。所有内容都自动写入又会造成噪声和隐私风险。我采用自动策略与工具查询结合的方式。Harness 在明确场景触发候选写入和召回，Agent 只在具体证据缺口下调用 `search_memory`。候选还要经过作用域、来源、稳定性和敏感性检查。

## 模拟面试使用方式

模拟面试每轮只回答一个问题。回答建议控制在一至三分钟，先给设计判断，再说明项目里的具体实现，最后补一个限制或取舍。面试官根据回答继续追问状态设计、故障场景、边界条件或验证方法。每轮结束后再复盘表达是否准确，避免一次背完整篇材料。

第一问

请你介绍一下这个多模式深度研究 Agent。
