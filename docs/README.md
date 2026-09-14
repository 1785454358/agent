# ResearchPilot 文档索引

项目正在重构为基于 LangGraph 的模块化 Research Agent Harness。当前只保留仍然约束目标架构、后续实施或求职讲解的文档。

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
5. [阶段 3：Workflow 与 Response 纵向切片](superpowers/plans/2026-09-12-workflow-response-vertical-slice.md)
   当前实施计划，覆盖 ResearchTopicGraph、Workflow 策略子图、Answer/Brief/Report 子图、引用校验和 Application Service 接入。

阶段 4 至阶段 8 在开始实施时，依据总体设计和路线图分别创建新的详细计划。不要复用已经删除的 Basic、Deep 或旧 Supervisor 方案作为新架构规格。

## 求职与面试材料

- [简历项目材料](resume/多模式深度研究Agent简历项目材料.md)
- [Harness 面试与学习指南](resume/多模式深度研究Agent面试与学习指南.md)

这两份文档描述项目最终形态。具体功能在代码和阶段退出测试完成前，不应当作已经交付的事实。

## 运行说明

- [项目入口与本地运行](../README.md)
- [后端配置、API 与分布式运行](../backend/README.md)

文档和示例不得包含真实 API Key、Cookie、访问令牌或其他凭据。
