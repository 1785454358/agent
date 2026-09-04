# DeepTrace 文档

当前项目只实现一种默认研究模式，研究策略对齐 GPT-Researcher BasicReport：一次规划搜索查询、并行搜索与抓取、Embedding 相关性过滤、统一上下文和一次报告写作。

当前有效文档：

- [默认 Basic 研究模式设计](superpowers/specs/2026-09-04-gpt-researcher-basic-flow-design.md)
- [真实问题与修复记录](q.md)
- [后端运行说明](../backend/README.md)

旧阶段文档已经删除。它们描述的 `ResearchNote`、Evidence、Claim、Verifier、任务级多轮 Researcher、覆盖率闭环和机械引用均不再属于目标架构。

新增研究模式必须单独设计，不提前在默认模式中预留复杂抽象。文档和示例不得包含真实 API Key。
