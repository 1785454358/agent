# 多模式深度研究 Agent 简历项目材料

## 推荐版本

**多模式深度研究 Agent｜独立开发｜2026.04–2026.09**

**技术栈：** Python、LangGraph、LangChain、FastAPI、Pydantic、SQLAlchemy、MySQL、Redis Streams、Chroma、BGE-M3、Tavily、Docker、Pytest

**项目描述：** 面向复杂开放问题构建可治理的 DeepResearch Agent Harness，支持 Workflow、Plan-and-Execute、Multi-Agent 三种研究策略，在有限预算下完成网页检索、原文查证、引用回答与结构化结果交付。

- **Shared Agent Loop：** 设计 `prepare_context → model → tools / finish → observe → policy` 循环，三种策略共享模型—工具执行器；通过有界补查、迭代上限、错误熔断和 `AgentOutcome` 管理完成、部分成功、失败与取消。
- **Context 工程：** 固定保留 system instruction、original task 与 current constraints，按完整工具交换裁剪历史并预留输出空间，避免上下文压缩破坏 tool-call / ToolMessage 协议。
- **Tool 治理：** 通过 ToolGateway 统一白名单、参数和 URL/SSRF 校验、三级预算、缓存、Singleflight、有界并发、transport retry、Execution Ledger 与 Evidence 落库。
- **稳定性与恢复：** 划分 transport retry、semantic repair、recovery replay 三类所有权；使用 Checkpoint 恢复控制状态，以 Ledger 复用已提交结果，不对任意外部副作用承诺 exactly-once。
- **Evidence 与 Eval：** 分离 State、Evidence、Memory 与执行记录，构建脚本化语料、故障注入和三策略对照评测；当前确定性测试 `482 passed, 2 deselected`，真实 Provider 质量独立验证。

## 精简版本

版面只够三条时使用：

- 基于 LangGraph 构建统一 Agent Harness，以 Session Graph 管理会话、记忆与策略路由，三种研究策略共享受控 Agent Loop。
- 通过 ModelGateway 与 ToolGateway 统一上下文信封、工具权限、URL 安全、预算、并发、重试、Ledger 和 Evidence 持久化。
- 使用 Checkpoint + Ledger 支持 at-least-once 场景恢复，以结构化 AgentOutcome 表达完成、部分成功、失败、取消和未完成计划。

## 30 秒项目介绍

我做的是一个可治理的 DeepResearch Agent Harness。它不是固定的搜索总结流程，而是让 Workflow、Plan-and-Execute、Multi-Agent 三种策略共享同一套模型调用、工具治理、上下文、预算、恢复和退出规则。项目重点解决三个工程问题：模型每轮看到什么、工具调用怎样受控、长任务失败后怎样恢复。当前通过 482 项确定性测试，并有脚本化三策略评测；真实 Provider 质量单独验证。

## 3 分钟项目介绍

项目处理的是需要多轮搜索、原文查证和引用回答的开放问题。顶层 Session Graph 管理会话生命周期、长期记忆和策略路由；Workflow、Plan-and-Execute、Multi-Agent 只负责不同的任务组织方式，每个研究分支进入统一 Shared Agent Loop。

循环每轮先装配 Context，再通过 ModelGateway 调用模型。模型可以更新待办、搜索或抓取；外部工具必须经过 ToolGateway，统一做白名单、参数和 URL 安全、预算、缓存、并发、重试、执行账本与 Evidence 落库。工具结果作为配对 ToolMessage 回写，Execution Policy 再决定继续、提醒或生成 AgentOutcome。

稳定性上，我把 transport retry、semantic repair、recovery replay 分给不同所有者。Checkpoint 保存控制状态，Ledger 保存已提交工具结果，避免恢复时盲目重复；但对任意第三方副作用不承诺 exactly-once。评测使用固定语料和故障注入，在统一预算下比较三种策略的完成、证据覆盖、引用有效性、调用和终止原因。

## 深挖时优先展开

### Agent 工程岗位

- 为什么“模型不再调用工具”不等于任务完成。
- 为什么上下文裁剪要以完整工具交换为单位。
- 为什么三种策略应该共享 Harness，而不是共享一个巨型 Graph。
- 为什么失败必须区分 transport、semantic 和 recovery。
- 为什么答案质量、执行成本和错误副作用要同时评估。

### 后端与可靠性岗位

- State、Runtime Context、Evidence、Ledger 与 Memory 的所有权划分。
- 预算预留、Singleflight、有界并发、稳定 call ID 和 at-least-once 恢复。
- MySQL、Redis Streams、Checkpoint、租约与取消传播的边界。
- 本地 Ledger 与分布式持久化 Ledger 的差别。

### 检索与知识岗位

- 搜索结果如何授权后续抓取，URL/SSRF 校验位于哪里。
- Evidence Store 为什么保存正文，而 Graph State 只保存 Evidence ID。
- citation validity、source coverage 与 faithfulness 的区别。
- 权威 Memory Store 与 Chroma 候选语义索引如何分工。

## 可以展示的项目证据

- [项目深度拆解](Agent%20Harness项目深度拆解.md)：完整系统故事与每节简历表达。
- [学习与面试路线](Agent%20Harness学习与面试路线.md)：源码、实验和面试证据准备顺序。
- [实现差距与完善清单](Agent%20Harness实现差距与完善清单.md)：完整方案与当前实现的事实边界。
- [Agent Harness 面试手册](Agent%20Harness面试手册.md)：高频追问和压力追问。
- [Agent Harness 源码学习指南](Agent%20Harness源码学习指南.md)：按调用链下钻实现。

## 事实边界

2026-09-22 的当前工作树执行 `uv run pytest -m "not real" -q`，结果为 `482 passed, 2 deselected in 43.42s`。这证明确定性契约和离线路径通过回归，不代表真实模型质量、线上吞吐或业务收益。

当前需要继续完善的重点包括：真实 Provider 固定基线、内容级 Prompt Injection 防护、通用 Human-in-the-loop 审批、精确 Token 成本计量和认证后的多租户隔离。具体状态和验收方法见实现差距清单。
