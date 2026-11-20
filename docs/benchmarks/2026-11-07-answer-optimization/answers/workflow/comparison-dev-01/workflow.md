# comparison-dev-01 / workflow

Using only the frozen documentation, compare Graph API and Functional API for a team needing branching/parallel visualization versus migrating existing procedural code.

Status: completed; answered: True; reason: None; model calls: 6; seconds: 29.539.

**结论：** 若团队首要需求是分支/并行可视化，选 Graph API；若首要需求是以最小改动迁移现有过程式代码，选 Functional API。冻结文档分别列出两者适用场景，但未就这两个场景给出直接对比或选型结论 [1]。

| 维度 | Graph API | Functional API |
|---|---|---|
| 分支/并行可视化 | 采用声明式方法，定义节点、边与共享状态以形成可视化图结构；多决策点分支显式且易可视化；并行运行后合并结果可自然处理；可视化便于团队理解、记录与维护 [1] | 采用命令式方法，将 LangGraph 功能集成到标准过程式代码；文档未提及专门的分支/并行可视化能力，仅列为“带简单分支逻辑的线性工作流” [1] |
| 迁移过程式代码 | 文档未直接说明其与现有过程式代码的对应关系或迁移方式 [1] | 明确适合对现有过程式代码做最小改动，使用 if/else、循环、函数调用等标准控制流，函数作用域状态 [1] |

**取舍条件：** 分支多、并行路径需汇合、可视化用于调试或文档协作时，Graph API 的显式结构更合适 [1]。已有过程式代码、希望少重构、工作流偏线性且分支简单时，Functional API 更合适 [1]。

**缺口：** 文档未给出两场景的直接对比或选型指引 [1]；也未说明 Graph API 迁移过程式代码的具体对应关系与迁移步骤 [1]。上述仅为本次可见材料范围，不能推出全部文档无答案。

## Sources

1. Choosing between Graph and Functional APIs — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/choosing-apis.mdx
