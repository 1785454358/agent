# comparison-dev-01 / multi_agent

Using only the frozen documentation, compare Graph API and Functional API for a team needing branching/parallel visualization versus migrating existing procedural code.

Status: completed; answered: True; reason: None; model calls: 5; tools: 3; seconds: 28.739.

**结论：** 若团队的核心诉求是分支/并行可视化，选 Graph API；若核心诉求是以最小改动迁移现有过程式代码，选 Functional API。两者共享同一底层运行时，可在同一应用中混用 [1]。

| 维度 | Graph API | Functional API |
|---|---|---|
| 分支/并行可视化 | 多个决策点的分支显式且易可视化；并行执行后合并结果可自然处理 [1] | 面向线性工作流与简单分支逻辑 [1] |
| 迁移过程式代码 | 声明式定义节点、边与共享状态 [1] | 命令式，明确用于对现有过程式代码做最小改动 [1] |
| 状态管理 | 显式共享状态，跨多节点协调 [1] | 函数作用域状态，无需显式状态管理 [1] |
| 团队协作 | 可视化便于理解、记录与维护复杂工作流 [1] | 未作为主要优势列出 [1] |
| 原型速度 | 未强调 | 样板代码少，适合快速原型 [1] |

**取舍条件：** 分支多、并行路径需汇合、可视化有助于团队理解时，Graph API 的显式结构是主要收益 [1]。代码已按 if/else、循环、函数调用组织且只需加入 LangGraph 能力时，Functional API 改动最小 [1]。

**双向迁移：** 文档给出 Functional→Graph（工作流变复杂时）与 Graph→Functional（图对简单线性流程过度复杂时）两条路径 [1]，说明选择可随复杂度调整，而非一次性锁定。

**边界：** 以上仅为冻结文档给出的适用场景描述，未提供性能、成本或迁移工作量的量化数据，无法据此做指标级比较。

## Sources

1. Choosing between Graph and Functional APIs — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/choosing-apis.mdx
