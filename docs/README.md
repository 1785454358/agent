# ResearchPilot 文档

项目提供三个平级研究模式。Basic 是参考 GPT-Researcher 的快速工作流；Deep 采用单 Agent Plan-and-Execute、ReAct 和动态重规划；Multi-Agent 采用 LangGraph Supervisor Plan-and-Execute、隔离的 ReAct Researcher 和反馈驱动的定向补查。

当前有效文档：

- [默认 Basic 研究模式设计](superpowers/specs/2026-09-04-gpt-researcher-basic-flow-design.md)
- [Deep 研究模式设计](superpowers/specs/2026-09-05-deep-research-design.md)
- [Deep 实施与验证计划](superpowers/plans/2026-09-05-deep-research.md)
- [Deep 首版验证记录](2026-09-05-deep-verification.md)
- [LangGraph Supervisor Plan-and-Execute 设计](superpowers/specs/2026-09-06-langgraph-supervisor-plan-execute-design.md)
- [LangGraph Supervisor Plan-and-Execute 实施计划](superpowers/plans/2026-09-06-langgraph-supervisor-plan-execute.md)
- [Supervisor Multi-Agent 首版验证记录](2026-09-06-supervisor-multi-agent-verification.md)
- [报告格式设计](../backend/docs/superpowers/specs/2026-09-05-report-format-and-run-summary-design.md)
- [报告格式实施计划](../backend/docs/superpowers/plans/2026-09-05-report-format-and-run-summary.md)
- [真实问题与修复记录](q.md)
- [后端运行说明](../backend/README.md)

旧阶段文档已经删除。`ResearchNote`、Evidence、Claim、Verifier 及旧覆盖率闭环不再属于目标架构。Deep 新增的是独立的规划与 ReAct 执行控制状态，并未恢复这些中间证据实体。

Basic、Deep、Multi-Agent 使用独立流程模块，只共享 Writer、数据模型、观测、工具、上下文、记忆和配置等基础能力。文档和示例不得包含真实 API Key。
