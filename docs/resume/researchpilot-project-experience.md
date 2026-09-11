# 多模式深度研究 Agent 简历材料

## 五条核心版本

**（1）多模式深度研究 Agent　　　　　　　　　独立开发　　　　　　　　　2026.04-2026.06**

**技术栈**　Python、LangGraph、LangChain、FastAPI、Pydantic、SQLAlchemy、MySQL、Redis Streams、Docker Compose、Function Calling、SSE、Pytest

**项目描述**　面向复杂开放问题构建可多轮追问的深度研究 Agent，以统一 Agent Harness 承载 Workflow、Plan-and-Execute、Multi-Agent 三种执行策略，完成检索、查证、回答及按需报告生成。

- **Agent Harness**　基于 LangGraph 构建 HarnessGraph，用统一 State、Runtime Context 和 Profile Registry 编排请求、路由、工具、记忆、响应与恢复，使三种策略共享运行协议并隔离子图状态。
- **三种研究 Profile**　将 Workflow、Plan-and-Execute、Multi-Agent 实现为固定流程、动态重规划、主管并行调度三类子图，支持按问题范围、研究深度与成本显式选择，并为 Auto 路由预留注册扩展点。
- **Tool Gateway 与 Evidence**　统一治理 `search_web`、`fetch_page`、`search_memory` 三个原子工具，执行参数、预算、重试和幂等校验；结果写入 Evidence Store，图状态只保留证据引用，使结论可回溯到来源原文。
- **记忆与上下文管理**　短期记忆以滑动窗口保留近期消息，达到压缩阈值时将历史整理为目标、事实与待办；长期记忆只在出现稳定偏好或可信事实时写入，按作用域组织，仅在当前意图需要历史信息时召回，并以版本、衰减和删除处理更新与遗忘。
- **持久化与可靠性**　MySQL 保存业务数据、Evidence、长期记忆、工具账本和 LangGraph Checkpoint，通过社区 `langgraph-checkpoint-mysql[asyncmy]` 接入；Redis Streams 负责投递与唤醒，结合幂等账本、租约和断点续跑处理重复消息及中断。

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
- **Multi-Agent**　Supervisor 维护任务依赖和完成状态，按研究方向并发调度 Researcher，再由 Writer 基于 Evidence 汇总结论；共享证据引用和任务进度，同时隔离各 Agent 的工作上下文。

### Tool Gateway 与 Evidence

- **原子工具治理**　Tool Gateway 只暴露搜索、抓取和记忆检索三个原子工具，在一次调用链中完成模式校验、参数规范化、预算预留、幂等去重、执行、结果校验和可观测事件记录。
- **图与工具的边界**　把带重规划和终止条件的复合研究过程建模为 LangGraph 子图，工具保持单一外部副作用，避免把隐藏循环包装成工具后失去节点级 Checkpoint 和轨迹。
- **证据与引用可信**　搜索摘要只用于发现候选来源，事实输入来自实际抓取正文或记忆中的有效原文片段；Evidence Store 保存正文、来源和内容哈希，Graph State 仅携带 Evidence ID，控制 Checkpoint 体积并支持引用回溯。

### 短期记忆与上下文

- **滑动窗口短期记忆**　以 thread 为边界保留最近若干轮原始消息，优先维持当前追问所需的指代、约束和用户反馈，超过窗口的内容转入摘要，防止历史消息持续占用模型上下文。
- **结构化动态压缩**　根据 Token 水位触发压缩，将早期对话整理为用户目标、已确认事实、约束条件、未解决问题和关键 Evidence 引用；新摘要基于旧摘要与被淘汰消息增量更新，并保留版本以便恢复。
- **多轮上下文装配**　每轮请求先合并会话摘要、近期消息、当前输入和按需召回的长期记忆，再交给选定 Profile；输出后更新窗口和摘要，使追问能够沿用已确认结论且不重复整段研究流程。

### 长期记忆

- **长期记忆写入策略**　仅在用户明确表达稳定偏好、关键事实被可靠证据支持或任务结束需要保存研究结论时生成候选记忆，经类型、置信度、来源和敏感性检查后写入，临时指令与未验证推断不进入长期存储。
- **长期记忆组织与召回**　按 user、workspace 和 global 命名空间组织偏好、事实与研究资料，结合语义相关性、关键词、时效、作用域和置信度排序；仅在意图判断需要历史信息时召回，并把结果作为带来源的候选上下文。
- **长期记忆更新与遗忘**　为记忆保存版本、来源、有效期和最后访问时间；新事实与旧记录冲突时追加新版本并降低旧版本权重，用户可显式更正或删除，系统按过期、长期未使用、低置信度和来源失效执行衰减或清理。

### 对话与输出

- **多轮意图路由**　区分新研究、追问、澄清、继续执行和报告请求，沿用同一 thread 的 Checkpoint 与证据集合；追问优先复用已有结论，研究目标发生变化时重新选择 Profile，发起新 run 或增量研究。
- **按需响应格式**　普通问答由 Response Graph 生成简洁回答并保留必要引用。用户明确提出报告要求时才进入 Report Graph，组织摘要、章节和完整参考来源，避免固定报告模板拖长日常回答。

### 持久化与可靠性

- **MySQL Checkpoint 恢复**　通过社区 `langgraph-checkpoint-mysql[asyncmy]` 实现的 `BaseCheckpointSaver` 适配器持久化 LangGraph Checkpoint，并在启动时执行表结构初始化和序列化兼容验证，使会话可按 thread 和 checkpoint 继续执行。
- **Redis 与 MySQL 分工**　Redis Streams 承担任务投递、消费者恢复、唤醒和取消通知，MySQL 保存权威状态；已写入账本的调用复用结果，具备幂等语义的工具按调用键去重，执行采用 at-least-once 投递且不承诺 exactly-once。
- **分层预算控制**　在模型和工具调用前统一预留调用次数、Token、时间和并发预算，并发请求通过预留、提交和释放避免额度竞争；超限时返回结构化原因及已有阶段性结果。
- **Checkpoint 与事件**　关键节点提交可恢复 State 和单调递增事件，客户端按事件 ID 续传进度；节点失败后从最近 Checkpoint 恢复，通过执行账本和调用键控制 at-least-once 投递产生的重复副作用。

### 可观测性与评测

- **结构化可观测性**　为每轮执行关联 run、thread、Profile、节点、模型调用、工具调用和 Evidence 标识，记录耗时、Token、重试、缓存命中与终止原因，用统一事件还原请求在 Harness 中的完整路径。
- **多 Profile 评测**　构建固定问题集与回放环境，在相同模型和工具配置下比较三种 Profile 的事实正确性、证据覆盖、任务完成度、Token、耗时及失败恢复表现，为策略选择和后续 Auto 路由提供依据。
