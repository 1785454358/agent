# 多模式深度研究 Agent 面试指南

这份材料按项目最终形态准备。项目基于 LangGraph 实现了一套统一 Agent Harness。这里的 Harness 是项目自行定义的运行治理层，负责规定状态、依赖、研究策略、模型调用、工具执行、证据、记忆、预算、恢复和观测怎样协作。LangGraph 提供状态图、子图、条件路由、Checkpoint 和持久化执行能力。

Workflow、Plan-and-Execute 和 Multi-Agent 是三种研究模式。每种模式由独立的研究策略子图实现。Answer、Brief 和 Report 是三种响应模式。研究模式决定怎样取得证据，响应模式决定怎样表达结果。

## 90 秒项目介绍

我做的是一个面向复杂开放问题的多模式深度研究 Agent。它会检索资料、读取原文、交叉验证并给出可追溯引用。默认输出简洁回答，用户明确要求时才生成正式报告。

项目基于 LangGraph 实现了一套统一 Agent Harness。LangGraph 负责状态图、策略子图和 Checkpoint。Harness 规定整次研究的运行协议，统一管理上下文、策略接入、模型与工具调用、证据、记忆、预算和恢复。

Workflow、Plan-and-Execute 和 Multi-Agent 分别实现为独立策略子图。它们接收统一的 `ResearchInput`，返回统一的 `ResearchOutcome`，因此能够共享 Tool Gateway、Evidence Store 和 Memory，同时隔离各自的计划与执行状态。

网页正文进入 Evidence Store，Graph State 只保存引用。Checkpoint 与幂等账本共同降低恢复后的重复调用风险。

## 3 分钟项目介绍

我做的是一个多模式深度研究 Agent，处理需要网页检索、原文阅读和交叉验证的复杂开放问题。普通请求返回简洁答案，用户明确要求报告时才进入 Report 响应图，研究深度和输出篇幅可以分别控制。

项目基于 LangGraph 实现统一 Agent Harness。LangGraph 提供 `StateGraph`、策略子图、条件路由、并发派发和 Checkpoint。Harness 定义项目自己的运行协议，管理 State 与运行依赖的边界，也统一研究策略、模型调用、工具执行、证据、记忆、预算、恢复和事件记录。

研究部分提供 Workflow、Plan-and-Execute 和 Multi-Agent 三种模式。`StrategyRegistry` 根据 `ResearchMode` 选择对应的策略子图。三个子图都接收 `ResearchInput`，结束时返回 `ResearchOutcome`。Workflow 的查询队列、Plan-and-Execute 的计划、Multi-Agent 的 Supervisor 与 Researcher 状态留在各自子图中，顶层 StateGraph 只理解公共契约。

节点通过 Runtime Context 获取依赖。模型调用进入 ModelGateway，工具调用进入 Tool Gateway。Tool Gateway 管理模式权限、参数与安全校验、幂等、预算、缓存和超时。Provider SDK 关闭内置重试，瞬时错误交给 LangGraph Node RetryPolicy。Evidence Store 保存经过规范化和分块的正文，Graph State 只保留 Evidence ID。

工作记忆属于可恢复 State，保存计划、任务进度、Finding、预算和未解决缺口。短期上下文使用滑动窗口与结构化压缩。长期记忆保存经过筛选的 Preference、Fact、Episode 和 Evidence 引用，并管理作用域、版本和遗忘。

MySQL 保存权威状态与执行账本，Redis Streams 负责任务投递。系统采用 at-least-once。Checkpoint 决定图从哪里继续，账本复用已提交的工具结果。外部服务成功而账本未提交时仍可能重复调用，写操作还需要 Provider 幂等键或补偿。

## 一次研究请求怎样经过 Harness

Harness 由一组共同执行的协议和模块边界组成。顶层 `StateGraph` 负责编排公共生命周期，其他边界分别治理依赖、调用、存储和恢复。

1. API 接收用户输入和 `ResearchMode`，生成 `run_id`，并使用 `thread_id` 关联 Checkpoint 与短期状态。同一 thread 的状态写入通过 MySQL Lease 串行化。
2. 顶层 `StateGraph` 恢复可序列化状态，清理上一轮临时字段，再规范化本次请求。
3. Context Middleware 根据 Token 预算装配近期消息、结构化摘要、Finding、Evidence ID 和未解决问题。Memory Router 只在当前意图需要历史信息时召回长期记忆。
4. 意图与研究路由判断已有证据是否足够。需要研究时，`StrategyRegistry` 根据 `ResearchMode` 解析 Workflow、Plan-and-Execute 或 Multi-Agent 策略子图。
5. 策略子图接收统一的 `ResearchInput`。内部计划、队列和 Agent 消息由子图私有 State 管理，运行依赖通过 Runtime Context 注入。
6. 模型节点调用 ModelGateway。工具节点调用 Tool Gateway。两个网关分别管理调用策略、超时、错误分类、事件与重试所有权。
7. Tool Gateway 先完成注册解析、模式权限、参数和安全校验，再查幂等账本并预留预算。随后处理缓存、Singleflight、Provider 执行和结果规范化。
8. Evidence Store 保存规范化、分块且有大小上限的网页正文。策略子图根据受控片段生成 Finding、引用和未解决缺口，并以 `ResearchOutcome` 返回顶层图。
9. 响应路由独立选择 Answer、Brief 或 Report。Writer 只存在于响应图。Multi-Agent 负责研究与结果聚合，不负责撰写最终回答。
10. 输出完成后，Memory Consolidation 更新短期摘要并筛选长期记忆候选。LangGraph 在节点边界保存 Checkpoint，事件系统记录模型、工具、预算和结束原因。

## Harness 模块边界

| 模块 | 负责什么 | 主要输入 | 主要输出 | 失败边界 |
| --- | --- | --- | --- | --- |
| 顶层 `StateGraph` | 编排请求规范化、上下文、研究路由、响应、记忆整理与结束状态 | Conversation State、Turn State、RunnableConfig | 更新后的 State、响应与运行终态 | 状态或权威存储无效时停止推进，策略失败统一转换为 partial 或 failed |
| `StrategyRegistry` | 根据强类型研究模式解析策略子图 | `ResearchMode`、策略注册信息 | `ResearchStrategyGraph` 或明确错误 | 拒绝未注册模式，不在内部兼容任意字符串 |
| Runtime Context | 向节点注入不可序列化的依赖 | 用户与工作区身份、网关、存储、事件接口、时钟 | 节点可访问的运行资源 | 依赖缺失时在节点入口失败，连接、客户端和锁不写入 State |
| State | 保存可序列化、可恢复的会话状态与工作记忆 | 节点更新、Reducer 合并结果 | Conversation State、Turn State、ResearchOutcome | 拒绝不兼容字段，大型正文和进程内对象不得进入 State |
| ModelGateway | 统一模型选择、结构化输出、超时、调用事件与重试所有权 | 模型请求、结构化 Schema、调用身份与预算 | 已校验模型结果、用量和事件 | SDK 重试设为零，瞬时错误交给对应模型节点的 RetryPolicy |
| Tool Gateway | 统一工具权限、参数、安全、预算、缓存、超时与幂等 | 工具名、规范化参数、调用身份和研究模式 | ToolResult、Evidence 引用、账本和事件 | 瞬时错误上抛给工具节点 RetryPolicy，超时不承诺远端已经取消 |
| Evidence Store | 唯一管理规范化、分块且受大小限制的正文记录 | 网页正文、来源元数据和内容哈希 | Evidence ID、版本、受控片段和有效状态 | 入库失败时不生成引用，失效证据不进入回答上下文 |
| Memory 子系统 | 管理短期上下文与长期记忆生命周期 | 消息、摘要、意图、Evidence 引用和记忆候选 | 上下文包、摘要、召回结果和版本化记忆 | 作用域不符、来源不足或敏感内容会被拒绝 |
| Checkpointer | 在节点边界保存 Graph State | thread、checkpoint namespace、状态和 pending writes | 可恢复快照与版本 | 写入失败时停止推进，防止状态与执行位置分叉 |
| Observability | 记录用户事件、Trace、Metric 和结构化 Log | thread、run、attempt、mode、节点、Agent 和工具标识 | SSE 事件、调用链、指标和诊断日志 | 关键审计事件无法持久化时按风险策略停止操作 |

## Harness 深挖回答

### 这个项目里的 Agent Harness 指什么

在这个项目里，Agent Harness 是一套可执行的运行协议。它约束一次研究使用什么 State，节点怎样取得依赖，研究策略怎样接入，模型和工具调用经过哪些治理步骤，证据与记忆由谁保存，失败后怎样恢复，以及整条执行链怎样被观察。

这些规则由顶层 StateGraph、Runtime Context、StrategyRegistry、ModelGateway、Tool Gateway、Evidence Store、Memory、Checkpointer 和事件系统共同实现。Harness 对应这些边界的协作规则，不对应单个类或单张图。判断一项能力是否属于 Harness，可以看它是否为多种研究策略提供共同的运行约束。

### Harness 和 LangGraph 分别负责什么

LangGraph 负责执行图。它提供 StateGraph、Node、Edge、Subgraph、Reducer、条件路由、并发派发、Checkpoint 和 interrupt。Workflow、Plan-and-Execute、Multi-Agent 以及响应流程都通过这些能力表达。

Harness 负责定义项目怎样使用这套执行能力。它规定 State 与 Runtime Context 的边界，研究策略的输入输出契约，模型和工具的调用规则，Evidence 与 Memory 的所有权，预算、错误、恢复和观测策略。LangGraph 让流程能够按图运行，Harness 让不同流程遵守同一套工程约束。

### 为什么三种研究模式都需要策略子图

三种模式都有可观察的状态变化和结束条件。Workflow 虽然路径固定，仍然包含查询生成、并发检索、原文获取、证据评估和补查上限。Plan-and-Execute 需要保存计划、任务结果和重规划次数。Multi-Agent 需要表达 Supervisor 派发、Researcher 并发和聚合。

把它们都实现为 LangGraph 子图后，每种策略都有清晰的 Checkpoint 边界、可测试路由和私有 State。顶层图只处理统一输入输出。项目也无需在 Python `while` 循环和 LangGraph 之间维护两套恢复与观测方式。

### 三种策略子图怎样共享能力并隔离状态

三个子图都接收 `ResearchInput`。其中包含研究问题、上下文摘要、已有 Evidence 引用、未解决缺口、预算和截止时间。它们都返回 `ResearchOutcome`，其中包含研究模式、Evidence ID、Finding、剩余缺口、执行步数和结束原因。

共享能力从 Runtime Context 获得，模型走 ModelGateway，工具走 Tool Gateway，正文进入 Evidence Store。隔离发生在子图内部。Workflow 的查询队列、Plan-and-Execute 的任务计划、Multi-Agent 的 Supervisor 和 Researcher 消息不会泄漏到顶层 State。这样可以独立修改一种策略，同时保持公共治理规则不变。

### 研究模式和响应模式为什么分开

研究模式决定怎样获得足够证据。响应模式决定怎样使用已有证据组织答案。Multi-Agent 可以执行深入研究并返回简洁 Answer，Workflow 得到的材料也可以在用户明确要求后进入 Report。

两者分开后，系统默认输出普通回答。Report 先检查 Evidence 是否覆盖用户要求的范围，范围不足时再运行当前研究策略补充材料。Writer 只属于 Answer、Brief 或 Report 响应图，不进入任何研究策略子图。

### Tool Gateway 为什么先校验再预留预算

Tool Gateway 的顺序是注册解析、模式权限、参数校验、安全检查、幂等账本查询、预算预留、缓存与 Singleflight、Provider 执行、Evidence 入库、预算提交或释放、事件记录。

权限、参数或安全检查失败的请求没有资格占用额度。通过校验以后先预留预算，可以防止多个并发 Researcher 同时看到相同余额并一起超限。幂等查询放在预留之前，已提交的成功结果可以直接复用。缓存命中与幂等命中分别记录，前者代表输入数据可复用，后者代表同一个逻辑调用已经完成。

Provider SDK 的重试设为零。Tool Gateway 负责超时和错误分类，瞬时错误继续抛给 LangGraph 工具节点的 RetryPolicy。这样一类错误只有一个重试层级。超时只能停止本地等待，远端请求仍可能完成，恢复时还要查询执行账本。

### 工作记忆为什么属于 State

工作记忆描述当前研究已经进行到哪里，包括计划、任务进度、Finding、Evidence ID、预算消耗、未解决缺口和停止原因。后续节点的路由与执行依赖这些字段，Worker 恢复后也需要它们继续任务。

这类信息具有业务含义，可以序列化，也需要随 Checkpoint 恢复，所以属于 LangGraph State。数据库连接、模型客户端、锁和时钟属于 Runtime Context。模型的隐藏推理不会写入 State。这个划分让 Checkpoint 保存足够的执行事实，同时避免把进程资源和不可控内容持久化。

### Evidence 正文为什么不能放进 State

网页正文可能很大。正文进入 State 后，每次 Checkpoint 都会重复序列化和写入，状态体积、数据库压力与恢复时间会随着研究过程增长。正文也容易被整个塞进模型上下文，挤占有效 Token。

Evidence Store 因此成为正文的唯一所有者。它负责 URL 规范化、内容哈希、分块、单块上限、总量上限、版本和有效状态。State 与长期记忆只保存 Evidence ID。节点按 ID 读取当前任务需要的受控片段。引用生成也只接受实际进入响应上下文的 Evidence。

### 滑动窗口和动态压缩怎样配合

滑动窗口保留最近若干轮原始消息，近期约束、修正和实体指代可以直接从原文读取。消息超过 Token 软阈值时，Context Middleware 将较早内容压缩成结构化摘要。摘要保存当前主题、用户约束、已确认事实、实体关系、未解决问题、此前结论和 Evidence ID。

压缩采用增量更新。系统根据旧摘要与本次移出窗口的消息生成新摘要，再检查结构和长度。达到硬阈值后，大型工具观察从模型上下文移除，只留下 Evidence 引用。近期原文负责局部语境，摘要负责稳定约束，Evidence Store 负责事实回溯。

### 长期记忆怎样覆盖完整生命周期

长期记忆需要回答六个问题。

何时存。用户明确要求记住，稳定偏好得到确认，可信 Evidence 支持的事实需要跨会话复用，或者研究结束后产生可复用经验时，系统才生成候选记忆。

存什么。长期记忆保存 Preference、Fact、Episode 和 Evidence 引用，并记录作用域、来源、置信度、时效状态、版本、到期时间和替代关系。临时表达、失败调用、无来源推断、敏感凭据、模型隐藏推理和 Evidence 正文不会写入。

如何组织。记忆按 user、workspace、thread 和 global 作用域隔离，再按类型建立 namespace。默认禁止跨用户或跨 workspace 召回。Global 只保存经过策略筛选且不含私人信息的研究经验。

何时召回。Memory Router 根据当前意图判断是否需要历史信息。检索先按 namespace、所有者、状态和时间过滤，并限制候选数量，再用本地 BGE-M3 结合关键词、来源质量与置信度进行评分和重排。Agent 遇到具体信息缺口时也可以调用 `search_memory`。

如何更新。Fact、Preference 和 Episode 采用版本化追加，新记录用 `supersedes` 关联旧版本。Evidence 的重新抓取和正文版本由 Evidence Store 管理，长期记忆只更新引用。用户修正和置信度变化都会留下审计轨迹。

如何遗忘。过期、来源失效、冲突替代、长期未采用和用户删除都会改变记忆状态。系统先降低召回权重，再按策略进行逻辑删除。用户删除或保留策略要求彻底清除时执行物理删除。

### Multi-Agent 为什么不允许 Supervisor 直接联网

Supervisor 负责拆分方向、分配任务、判断覆盖范围和决定是否结束。Researcher 负责检索、阅读和形成局部 Finding。如果 Supervisor 也能直接联网，任务分派和证据生产会混在同一个状态里，预算归属、来源去重与失败重试都更难解释。

项目让 Supervisor 只能通过结构化任务调用 Researcher。Researcher 的工具调用统一经过 Tool Gateway，结果以 Evidence ID、Finding 和未解决缺口返回。这样每次联网行为都有明确的 Agent、任务、预算与幂等身份，Supervisor 的上下文也不会被大量网页正文占满。

### Checkpoint 和幂等账本怎样配合恢复

Checkpoint 保存图在节点边界的可恢复状态，工具执行账本保存已经提交的调用结果。Worker 中断后，新 Worker 使用相同的 `thread_id` 从最近 Checkpoint 恢复。工具节点根据 run、节点、任务、工具名和规范化参数生成稳定幂等键，先查账本再决定是否执行。

工具调用前崩溃时，恢复后重新进入节点。Provider 已经成功而账本尚未提交时，恢复可能再次请求。账本已经提交而 Checkpoint 尚未提交时，恢复会用相同幂等键复用结果。Checkpoint 无法独自覆盖后两个外部副作用窗口。

支持幂等键的 Provider 可以抑制重复写入。其他写操作需要 Outbox 配合幂等消费者，也可以使用补偿或人工确认。搜索和抓取属于只读调用，重复不会改变远端业务状态，但可能增加费用。

### 为什么选择 MySQL Checkpointer，它有哪些限制

项目已有 MySQL 技术栈，业务状态、工具账本、长期记忆和 Checkpoint 可以由同一套权威数据库管理。LangGraph 提供 `BaseCheckpointSaver` 扩展接口，项目使用社区维护的 `langgraph-checkpoint-mysql[asyncmy]` 实现所需的异步 Checkpointer 能力。部署固定适配器版本，数据库使用 MySQL 8.0.19 及以上，并在启动阶段执行 `setup()`。

社区实现需要项目自行验证兼容性。契约测试覆盖 State 序列化、`thread_id`、checkpoint namespace、pending writes 和异步并发行为。升级 LangGraph 或适配器前先运行回归测试。故障注入会在 Planner 后、工具成功后、部分 Researcher 完成后和 Report Writer 前中断 Worker，再检查恢复位置与重复调用。

这个依赖只提供 Checkpointer。长期记忆由项目自建的 MySQL Memory Store 与 Repository 管理。面试时只说明经过测试的能力，不宣称官方内置 MySQL 支持，也不宣称社区实现覆盖最新接口的全部行为。

### Redis 和 MySQL 怎样分工

MySQL 是权威状态源，保存会话、运行记录、Checkpoint、Evidence、长期记忆和工具执行账本。Evidence 表由 Evidence Store 独占访问，Memory Store 只保存 Preference、Fact、Episode 和 Evidence 引用。

Redis Streams 承担任务投递、消费者组、Worker 唤醒和取消通知。Worker 收到消息后仍需到 MySQL 获取运行状态与 Lease。Redis 消息丢失或重复不会改变最终事实。Recovery Scanner 可以根据 MySQL 中未完成且 Lease 已过期的 run 重新投递。

### 为什么采用 at-least-once，无法承诺 exactly-once

Redis Streams 的消息在消费者确认前可能被其他 Worker 重新认领。Worker 也可能在外部调用成功后、确认消息或提交 Checkpoint 前崩溃。同一个节点因此可能执行多次。

项目通过 Checkpoint、Lease、稳定幂等键和执行账本降低重复影响。Provider 已经成功而账本尚未提交时，恢复仍可能再次调用。这个窗口决定了系统只能承诺 at-least-once。搜索和抓取能够容忍效果重复，涉及远端写入时还需要 Provider 幂等键、Outbox、补偿或人工确认。

### 怎样比较三种研究模式

评测使用固定问题集，覆盖事实检索、多约束比较、执行中出现新证据缺口的问题，以及适合并行拆分的问题。三种模式使用相同模型版本、工具 Provider、预算口径和 Evidence 规则，让差异主要来自研究策略。

质量侧检查事实正确性、Evidence 覆盖、引用有效性、未解决缺口和任务完成度。成本侧记录模型 Token、工具次数、抓取页数和重复来源。时延侧记录总耗时、首个有效 Evidence 时间和并发利用率。恢复测试记录中断后的重复调用与最终结果。评测结果用于说明适用边界，也为后续 Auto 模式提供基线。

## 三种研究模式怎样选择

| 研究模式 | 适合的问题 | 主要优势 | 主要代价 |
| --- | --- | --- | --- |
| Workflow | 范围清楚、步骤稳定、需要快速查证的问题 | 路径短，行为容易预测，成本边界清楚 | 不会动态重规划，面对开放缺口时适应能力有限 |
| Plan-and-Execute | 目标明确，需要分步查证，执行中可能发现新缺口的问题 | 计划与证据缺口可见，可以根据评估结果调整后续步骤 | 多次规划和评估会增加模型调用与时延 |
| Multi-Agent | 可以按方向拆分、来源较多、并行研究收益明显的问题 | Researcher 隔离上下文并发工作，Supervisor 统一判断覆盖范围 | 协调、聚合和重复检索成本更高，需要严格预算与去重 |

三种模式保持显式可选，用户可以按问题复杂度、成本和时延要求选择，评测结果也能直接对应具体策略。Auto 模式需要稳定的质量标签和成本基线，因此放在三种模式形成可靠评测以后设计。

## 关键取舍

### 为什么复合研究流程做成子图

搜索和抓取是原子外部能力，适合注册为 Tool。查询生成、并行搜索、证据评估、补查和结束判断包含独立状态与循环，适合放进研究策略子图。整段研究如果被包装成一个复合工具，顶层执行只能看到一次黑盒调用，内部节点也难以单独保存 Checkpoint、控制预算和记录事件。

### MySQL 社区适配器带来什么取舍

沿用 MySQL 可以减少数据库依赖，并让运行状态与工具账本使用同一个权威数据源。社区 Checkpointer 的兼容性与升级风险需要项目承担。适配器位于 Infrastructure 层，Harness 只依赖 Checkpointer 协议，契约测试和故障恢复测试负责锁定项目使用的行为。以后更换实现时，三种研究策略无需修改。

### 记忆自动化怎样保持可控

长期记忆采用自动策略与工具查询结合的方式。Harness 在明确场景生成写入或召回候选，Agent 只在具体信息缺口下调用 `search_memory`。所有候选都要经过作用域、来源、稳定性和敏感性检查。这个设计降低漏存概率，也限制临时内容进入长期记忆。

## 模拟面试使用方式

模拟面试每轮只回答一个问题。回答控制在一至三分钟，先给设计判断，再说明项目中的具体实现，最后补一个限制或取舍。面试官可以要求缩短答案、指出漏洞或切换到压力面。每轮结束后再复盘表达是否准确。

第一问

请你介绍一下这个多模式深度研究 Agent。
