# ResearchPilot 文档索引

项目已经完成基于 LangGraph 的模块化 Research Agent Harness 主体重构。当前文档分为架构规格、实施记录、运行说明和求职讲解四类。

## Harness 重构必需文档

建议按以下顺序阅读：

1. [Harness 总体设计](superpowers/specs/2026-09-10-langgraph-agent-harness-refactor-design.md)
   定义 Harness、LangGraph、顶层运行图、策略子图、State、Memory、Tool Gateway、Checkpoint 与三种研究模式的职责边界，是重构的唯一总体规格。
2. [Harness 交付路线图](superpowers/plans/2026-09-10-langgraph-agent-harness-roadmap.md)
   将完整重构拆成八个阶段，并定义各阶段的退出条件。
3. [阶段 1：Harness Foundation](superpowers/plans/2026-09-10-agent-harness-foundation.md)
   记录领域契约、Harness State、Runtime Context、Strategy Registry 和顶层运行图骨架的实现要求。该阶段已完成，保留用于解释基础契约。
4. [阶段 2：Tool Gateway 与 Evidence Store](superpowers/plans/2026-09-10-tool-gateway-evidence-store.md)
   记录统一工具管道、权限、安全、预算、幂等、缓存、Singleflight 和 Evidence 所有权。该阶段已完成，后续策略子图必须遵守这些契约。
5. [Harness 实现决策记录](superpowers/plans/2026-09-13-harness-implementation-decisions.md)
   记录八阶段实现、审查与可靠性修复的最终决定。
6. [Chroma 长期记忆实施计划](superpowers/plans/2026-09-14-chroma-long-term-memory.md)
   记录 MySQL 结构化过滤、BGE-M3 向量生成、Chroma TopK 和 MySQL 回查链路。

## 求职与面试材料

- [简历项目材料](resume/多模式深度研究Agent简历项目材料.md)
- [Harness 面试与学习资料](resume/多模式深度研究Agent面试与学习资料/00-阅读目录.md)
- [作品展示制作指南](resume/作品展示制作指南.md)

求职材料以当前代码和测试为事实边界。自动遗忘调度、认证身份隔离和 Auto 模式仍属于后续能力。

## 运行说明

- [项目入口与本地运行](../README.md)
- [后端配置、API 与分布式运行](../backend/README.md)

文档和示例不得包含真实 API Key、Cookie、访问令牌或其他凭据。
