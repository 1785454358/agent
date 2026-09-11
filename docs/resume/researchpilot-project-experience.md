# 多模式深度研究 Agent 简历材料

## 五条核心版本

**（1）多模式深度研究 Agent　　　　　　　　　独立开发　　　　　　　　　2026.04-2026.06**

**技术栈**　Python、LangGraph、LangChain、FastAPI、Pydantic、SQLAlchemy、MySQL、Redis Streams、BGE-M3、Docker Compose、Function Calling、SSE、Pytest

**项目描述**　面向复杂开放问题构建可多轮追问的深度研究 Agent，以统一 Agent Harness 承载 Workflow、Plan-and-Execute、Multi-Agent 三种执行策略，完成检索、查证、回答及按需报告生成。

- **Agent Harness**　基于 LangGraph 构建 HarnessGraph，用统一 State、Runtime Context 和 Profile Registry 编排请求、路由、工具、记忆、响应与恢复，使三种策略共享运行协议并隔离子图状态。
- **三种研究 Profile**　将 Workflow、Plan-and-Execute、Multi-Agent 实现为固定流程、动态重规划、主管并行调度三类子图，支持按问题范围、研究深度与成本显式选择，并为 Auto 路由预留注册扩展点。
- **Tool Gateway 与 Evidence**　模型调用与工具调用分别经过 ModelGateway 和 Tool Gateway；网关处理参数、预算、幂等、超时与错误分类，临时故障仅由 LangGraph Node RetryPolicy 重放工具节点；Evidence Store 统一保存规范化、分块且有大小上限的正文，图状态只保留证据引用。
- **记忆与上下文管理**　短期记忆以滑动窗口保留近期消息，达到压缩阈值时将历史整理为目标、事实与待办；长期记忆只在出现稳定偏好或可信事实时写入，按作用域组织，仅在当前意图需要历史信息时召回，并以版本、衰减和删除处理更新与遗忘。
- **持久化与可靠性**　MySQL 保存权威业务状态、Evidence 元数据、检索索引与正文记录、长期记忆和工具账本，版本锁定的社区 `langgraph-checkpoint-mysql[asyncmy]` 仅接入项目所需 Checkpointer 能力；Redis Streams 负责投递与唤醒，结合租约、Checkpoint 和幂等账本识别并降低重复执行影响。

## 可选项目要点库

以下要点可根据岗位要求和简历版面替换，建议最终保留五至七条。

### Agent Harness

- **统一执行生命周期**　将请求规范化、意图识别、Profile 路由、上下文装载、工具调用、响应生成、记忆写入和事件记录编排为 HarnessGraph，集中处理横切能力，避免三种策略各自维护一套运行逻辑。
- **状态与运行上下文**　用可序列化 State 保存可恢复的业务状态，以 Runtime Context 注入模型、工具、时钟和存储依赖，区分持久状态与进程内资源，便于测试、恢复和替换基础设施。
- **Profile Registry 与子图隔离**　通过注册表按统一输入输出契约挂载 Workflow、Plan-and-Execute、Multi-Agent 子图；父图只接收标准 ResearchOutcome，子图私有规划和协作状态不泄漏到共享 State。
- **统一 LangGraph 编排**　三种策略的循环、条件分支、并发派发、人工确认和恢复边界均由 LangGraph 表达，Checkpoint 能落在确定节点，避免手写循环绕开状态机和执行记录。

### Research Profile

- **Workflow**　将查询改写、并行检索、证据筛选和完整性评估固化为短路径图，适合边界清晰、时效要求高的研究问题，并通过统一 Harness 获得工具治理、记忆和恢复能力。
- **Plan-and-Execute**　Planner 先生成结构化任务计划，Executor 逐项执行并回写发现，Replanner 根据证据缺口调整剩余步骤，在调用预算和终止条件内处理需要多轮查证的问题。
- **Multi-Agent**　Supervisor 维护任务依赖和完成状态，按研究方向并发调度 Researcher，聚合各任务的 Evidence、Finding 与未解决缺口并返回统一 ResearchOutcome，同时隔离各 Agent 的工作上下文。

### Tool Gateway 与 Evidence

- **原子工具治理**　Tool Gateway 只暴露搜索、抓取和记忆检索三个原子工具，负责参数、权限、预算、幂等、超时和错误分类；Provider SDK 内置重试设为 0，临时异常交由 LangGraph Node RetryPolicy 重放节点。
- **图与工具的边界**　把带重规划和终止条件的复合研究过程建模为 LangGraph 子图，工具保持单一外部副作用，避免把隐藏循环包装成工具后失去节点级 Checkpoint 和轨迹。
- **证据与引用可信**　搜索摘要只用于发现候选来源；Evidence Store 是正文唯一所有者，统一保存规范化、分块且有大小上限的正文、来源和内容哈希，Graph State 与长期记忆仅携带 Evidence ID，控制 Checkpoint 体积并支持引用回溯。

### 短期记忆与上下文

- **滑动窗口短期记忆**　以 thread 为边界保留最近若干轮原始消息，优先维持当前追问所需的指代、约束和用户反馈，超过窗口的内容转入摘要，防止历史消息持续占用模型上下文。
- **结构化动态压缩**　根据 Token 水位触发压缩，将早期对话整理为用户目标、已确认事实、约束条件、未解决问题和关键 Evidence 引用；新摘要基于旧摘要与被淘汰消息增量更新，并保留版本以便恢复。
- **多轮上下文装配**　每轮请求先合并会话摘要、近期消息、当前输入和按需召回的长期记忆，再交给选定 Profile；输出后更新窗口和摘要，使追问能够沿用已确认结论且不重复整段研究流程。

### 长期记忆

- **长期记忆写入策略**　仅在用户明确表达稳定偏好、关键事实被可靠证据支持或任务结束需要保存研究结论时生成候选记忆，经类型、置信度、来源和敏感性检查后写入，临时指令与未验证推断不进入长期存储。
- **长期记忆组织与召回**　按 user、workspace 和 global 命名空间组织 Preference、Fact、Episode 与 Evidence 引用；MySQL 先按作用域和时间筛选有界候选集，再由本地 BGE-M3 做语义重排，仅在当前意图需要历史信息时召回。
- **长期记忆更新与遗忘**　为记忆保存版本、来源、有效期和最后访问时间；新事实与旧记录冲突时追加新版本并降低旧版本权重，用户可显式更正或删除，系统按过期、长期未使用、低置信度和来源失效执行衰减或清理。

### 对话与输出

- **多轮意图路由**　区分新研究、追问、澄清、继续执行和报告请求，沿用同一 thread 的 Checkpoint 与证据集合；同一 thread 仅允许一个修改状态的 active run 持有 MySQL Lease，后续请求排队，避免并发覆盖会话状态。
- **按需响应格式**　普通问答由 Response Graph 生成简洁回答并保留必要引用。用户明确提出报告要求时才进入 Report Graph，组织摘要、章节和完整参考来源，避免固定报告模板拖长日常回答。

### 持久化与可靠性

- **MySQL Checkpoint 恢复**　在 MySQL 8.0.19 及以上版本使用社区 `langgraph-checkpoint-mysql[asyncmy]` 接入项目所需核心 Checkpointer 能力，通过版本锁定、`setup()`、契约测试和故障注入验证恢复行为；长期记忆由自建 MySQL Memory Store 管理。
- **Redis 与 MySQL 分工**　Redis Streams 承担任务投递、消费者恢复、唤醒和取消通知，MySQL 保存权威状态；采用 at-least-once 投递，账本仅复用已提交成功结果，Provider 成功但账本未提交的窗口仍可能重复调用。
- **分层预算控制**　在模型和工具调用前统一预留调用次数、Token、时间和并发预算，并发请求通过预留、提交和释放避免额度竞争；超限时返回结构化原因及已有阶段性结果。
- **Checkpoint 与事件**　关键节点提交可恢复 State 和单调递增事件，客户端按事件 ID 续传进度；节点失败后从最近 Checkpoint 恢复，通过执行账本和调用键识别并降低 at-least-once 投递造成的重复影响。

### 可观测性与评测

- **结构化可观测性**　为每轮执行关联 run、thread、Profile、节点、模型调用、工具调用和 Evidence 标识，记录耗时、Token、重试、缓存命中与终止原因，用统一事件还原请求在 Harness 中的完整路径。
- **多 Profile 评测**　构建固定问题集与回放环境，在相同模型和工具配置下比较三种 Profile 的事实正确性、证据覆盖、任务完成度、Token、耗时及失败恢复表现，为策略选择和后续 Auto 路由提供依据。
