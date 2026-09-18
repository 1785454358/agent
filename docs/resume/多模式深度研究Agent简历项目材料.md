# 多模式深度研究 Agent 简历项目材料

## 推荐版本

**多模式深度研究 Agent｜独立开发｜2026.04–2026.09**

**技术栈：** Python、LangGraph、LangChain、FastAPI、Pydantic、SQLAlchemy、MySQL、Redis Streams、Chroma、BGE-M3、Tavily、Docker、Pytest

**项目描述：** 面向复杂开放问题构建多模式深度研究 Agent，通过统一 Agent Harness 完成网页检索、原文查证、引用回答和按需报告生成。

- **统一运行架构：** 基于 LangGraph 构建 Session Graph，集中管理上下文、记忆、策略路由与响应；Workflow、Plan-and-Execute、Multi-Agent 三种编排策略共享同一个 Agent Loop，并通过强类型输入输出隔离私有状态。
- **模型与工具治理：** 所有生产模型调用通过 ModelGateway，强制携带 system instruction、original task 和 current constraints；外部工具通过 ToolGateway 统一执行白名单、参数与 URL/SSRF 校验、三级预算、缓存、Singleflight、超时和执行账本。
- **受控 Agent Loop：** 实现 `prepare_context → model → tools/finish → observe → execution policy` 循环；无依赖工具有界并行，依赖调用等待前置结果，并保证每个 tool call 都有按原顺序闭合的 ToolMessage。
- **错误与恢复：** 明确 transport retry、semantic repair、recovery replay 三层归属；使用 Checkpoint 保存可恢复 State，Ledger 重放已提交工具结果，所有受控退出生成包含状态、证据、错误、预算和计划完成度的 AgentOutcome。
- **证据与记忆：** Evidence Store 保存正文和来源，Graph State 只携带 Evidence ID；实现会话窗口与结构化摘要、用户偏好和研究事实的长期记忆，以及 MySQL/SQLite 权威记录与 Chroma 语义索引分工。

## 精简版本

版面只够三条时使用：

- 基于 LangGraph 构建统一 Agent Harness，以 Session Graph 管理会话、记忆与策略路由，三种研究策略共享受控 Agent Loop。
- 通过 ModelGateway 与 ToolGateway 统一模型信封、工具权限、URL 安全、预算、并发、重试、幂等账本和 Evidence 落库。
- 使用 Checkpoint + Ledger 支持 at-least-once 场景恢复，以结构化 AgentOutcome 表达完成、部分成功、失败、取消和未完成计划。

## 按岗位替换的要点

### Agent 工程岗位

- 将 system instruction、original task、current constraints 固定为模型调用不变量，按完整工具交换裁剪历史，避免上下文压缩破坏协议。
- 将临时传输失败交给 Gateway，语义修复交给 Agent Loop，崩溃重放交给 Checkpoint/Worker/Ledger，避免多层重复重试。
- 用有界 completion nudge、迭代上限、连续错误熔断和结构化 Outcome 控制开放式模型循环。

### 后端与可靠性岗位

- 使用可序列化 State 和 Runtime Context 分离业务恢复状态与进程资源，策略子图通过统一输入输出接入顶层运行图。
- 通过工具预算预留、Singleflight 和稳定 call ID 控制并发消耗；Ledger 重放已提交结果，降低 at-least-once 投递的重复影响。
- 分布式模式使用 MySQL 保存权威状态、Redis Streams 投递任务和传播取消信号；不对任意外部副作用承诺 exactly-once。

### 检索与知识岗位

- 将网页正文、来源和内容哈希保存到 Evidence Store，研究状态和记忆只引用 Evidence ID，响应仅允许引用本轮已加载证据。
- 长期记忆先按 namespace、类型、状态和有效期过滤，再在候选内通过 BGE-M3 与 Chroma 做语义 TopK，命中后回查权威 Store。

## 事实边界

当前记录的离线测试基线为 `464 passed, 1 deselected`，覆盖三种策略、模型上下文信封、工具配对、Gateway 边界、AgentOutcome 和 Checkpoint 恢复。

以下能力只应写为演进方向：认证后的多租户隔离、通用 Human-in-the-loop 审批、完整内容级 Prompt Injection 检测、Provider 精确 Token 成本计量、真实服务性能结论和系统化在线 Agent Eval。

面试展开材料见 [Agent Harness 面试手册](Agent%20Harness面试手册.md)，实现路径见 [源码学习指南](Agent%20Harness源码学习指南.md)。
