# Agent Harness 面试手册

## 一句话介绍

这是一个基于 LangGraph 的多模式深度研究 Agent：Session Graph 管理会话、记忆和策略路由，Workflow、Plan-and-Execute、Multi-Agent 三种编排策略共享同一个受治理的 Agent Loop，所有模型和外部工具调用分别经过 ModelGateway 与 ToolGateway。

## 90 秒介绍

项目解决的重点是把 Agent 运行中容易失控的横切能力收敛到统一 Harness。顶层 Session Graph 管理上下文压缩、意图、长期记忆、策略选择和响应；三个策略只负责如何拆解和协调研究任务，它们都把具体研究分支交给 Shared Agent Loop。

Agent Loop 每轮固定经过上下文准备、ModelGateway、工具分发、观察和执行策略。模型能更新计划、搜索和抓取，但系统强制保留原始任务与当前约束，限制迭代、并发和预算，并保证每个 tool call 都有 ToolMessage。外部工具统一经过 ToolGateway，执行权限、URL 安全、预算、缓存、Singleflight、重试、Ledger 和 Evidence 落库。

恢复方面，Checkpoint 保存可恢复 State，Execution Ledger 重放已提交的工具结果。所有受控退出都产生结构化 AgentOutcome，而不是只返回一个停止原因。当前离线测试基线是 464 passed、1 deselected；真实 Provider 与外部服务单独验证。

## 五个核心问题

### 1. Harness 和 LangGraph 分别负责什么？

LangGraph 提供 StateGraph、条件边、并行派发和 Checkpoint 机制。Harness 是项目定义的运行协议和治理层，决定 State 与 Runtime Context 的边界、模型和工具入口、预算、记忆、错误分类、恢复与退出不变量。Harness 使用 LangGraph 实现，但不等于 LangGraph 本身。

### 2. 为什么三个策略共享一个 Agent Loop？

Workflow、Plan-and-Execute、Multi-Agent 的差别是任务拆解和协调方式，不是搜索、抓取、上下文裁剪和错误治理方式。共享 Loop 可以让三种策略天然遵守相同的模型信封、工具权限、预算、配对、恢复和 Outcome 契约，避免修复一套逻辑却遗漏另外两套。

### 3. 三种 retry 怎样划分？

- transport retry 属于 ModelGateway / ToolGateway，只处理临时网络与服务错误；
- semantic repair 属于 Agent Loop，把结构化失败回灌给模型，由模型修正参数、查询或来源；
- recovery replay 属于 Checkpoint / Worker / Ledger，用于进程崩溃和 at-least-once 重放。

这样可以避免模型、网关和 Worker 对同一次失败同时重试，造成调用放大。

### 4. 为什么工具批不是全部串行？

同批无依赖调用使用信号量有界并行。依赖关系仍被保留：`fetch_page` 如果要使用同批 `search_web` 新发现的 URL，就等待搜索完成和授权更新。结果按原 tool-call 顺序写回，因此并发不会破坏模型轨迹的确定性。

### 5. AgentOutcome 为什么不能只有 stop_reason？

停止原因只能解释“为什么停”。上层还需要判断结果能否使用、有什么证据、发生了什么错误、消耗多少步骤、计划完成多少以及是否能继续。因此 Outcome 同时包含 status、summary、evidence、errors、iterations、budget、plan completion 和 unfinished todos。

## 高频追问

### 每次模型调用怎样保证上下文完整？

Context Policy 固定构造 system instruction、original task 和 current constraints，并按完整工具交换裁剪历史。ModelGateway 在 Provider 调用前再次检查这三个条件，防止某个策略节点绕过约束。

### `write_todos` 为什么不经过 ToolGateway？

它只修改循环内可恢复状态，没有网络、文件、数据库或其他外部副作用。`search_web` 和 `fetch_page` 会访问外部资源，必须经过 ToolGateway。这个划分依据是副作用和治理需求，不是模型是否以 tool call 形式调用。

### 怎样保证 tool call 闭合？

执行器为调用补全稳定 ID，并为成功、参数错误、未知工具、取消和终止错误都生成 ToolMessage。Context Policy 只接收完整的 assistant 调用批和全部结果；未配对批次会触发上下文错误并产生 Outcome。

### ModelGateway 和 ToolGateway 的职责有什么不同？

ModelGateway 管理模型角色参数、工具绑定、上下文信封、超时和模型传输错误。ToolGateway 管理外部能力的权限、安全、预算、幂等、缓存、并发、证据和工具传输错误。策略节点不得直接调用生产模型或外部工具 Provider。

### Checkpoint 为什么不能单独解决重复调用？

Checkpoint 只能恢复图状态。如果 Provider 已成功但节点还没提交 Checkpoint，恢复后仍可能重复执行。Ledger 用稳定 call ID 记录已提交的工具结果，恢复时优先重放结果。系统降低重复影响，但不对任意外部副作用承诺 exactly-once。

### State、Runtime Context、Evidence Store 怎样分工？

- State 保存可序列化且需要恢复的控制信息；
- Runtime Context 注入模型、Gateway、Store、时钟等运行资源；
- Evidence Store 保存正文和来源，State 只携带 Evidence ID。

这样既能恢复控制流，又不会把大正文和不可序列化连接塞进 Checkpoint。

### 上下文管理和长期记忆是什么关系？

上下文管理控制单次模型视图，负责窗口、摘要和 Token 预算。长期记忆跨会话保存用户偏好与带证据事实，按意图召回。召回结果是可裁剪背景，原始任务和当前约束始终固定保留。

### Workflow、Plan-and-Execute、Multi-Agent 怎样选择？

- 问题边界清晰、追求较短路径时用 Workflow；
- 需要多步查证和根据缺口调整计划时用 Plan-and-Execute；
- 能拆成多个相对独立研究方向时用 Multi-Agent。

Multi-Agent 不天然更好。方向耦合强或预算小的时候，协调成本可能高于收益。

### Multi-Agent 怎样控制竞争和重复消耗？

每个 Researcher 使用独立分支状态和 caller identity，通过 Reducer 合并结果；共享 Gateway 负责并发限制、预算原子预留、Singleflight 和 Ledger。Supervisor 只负责任务拆解与评估，不直接使用联网工具。

### 工具失败后系统怎样继续？

临时网络错误先在 ToolGateway 做有限退避；校验、权限、预算或业务失败被转换成结构化 ToolMessage。Agent 可以据此换参数或换来源。连续错误达到阈值后 Execution Policy 熔断并返回 partial 或 failed Outcome。

### 引用可信怎样保证？

网页正文由 Evidence Store 持有，研究 State 只保存 Evidence ID。响应只能引用本轮允许并成功加载的证据；未知或失效引用不会被补造。证据不足时返回部分结果和明确缺口。

### 当前最大的限制是什么？

当前离线测试证明运行不变量和主要治理逻辑，但真实模型与外部服务需要独立凭据和环境。认证后的租户隔离、通用 Human-in-the-loop、完整内容级 Prompt Injection 检测、精确 Token 成本计量和系统化在线评测仍是演进方向。

## 压力追问

### 这是否只是把代码包了一层？

如果只做统一函数调用，确实只是封装。这里的价值来自可验证的运行不变量：模型上下文完整、外部调用经过 Gateway、工具调用闭合、退出有 Outcome、恢复后不变量仍成立。它改变了失败、恢复和审计方式。

### 为什么不用一个巨大的 Graph？

顶层 Graph 只管理会话生命周期，策略 Graph 管理任务编排，Shared Agent Loop 管理模型—工具循环。三层用强类型输入输出衔接。这样可以单独测试、替换策略，并避免策略私有状态污染全局 State。

### 为什么不把研究流程封装成一个大工具？

大工具会隐藏循环、重试和中间状态，Checkpoint 只能看到开始和结束。将循环显式建模后，每轮模型调用、工具批、观察和退出都可追踪、限额和恢复。

## 表述边界

面试时使用以下措辞：

- 可以说“离线测试覆盖并验证”，不要说“所有真实服务已通过生产验收”。
- 可以说“Ledger 降低 at-least-once 下的重复影响”，不要承诺任意副作用 exactly-once。
- 可以说“实现工具白名单、URL/SSRF 校验与信封隔离”，不要声称已完整解决 Prompt Injection。
- 可以说“AgentOutcome 提供调用与步骤预算快照”，不要把估算写成 Provider 精确 Token 账单。

继续下钻实现时，使用[源码学习指南](Agent%20Harness源码学习指南.md)。
