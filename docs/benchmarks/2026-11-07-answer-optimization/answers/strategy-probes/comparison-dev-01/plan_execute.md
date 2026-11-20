# comparison-dev-01 / plan_execute

Using only the frozen documentation, compare Graph API and Functional API for a team needing branching/parallel visualization versus migrating existing procedural code.

Status: completed; answered: True; reason: None; model calls: 9; seconds: 44.770.

**结论：** 若团队首要需求是分支/并行路径的可视化，选 Graph API；若首要需求是以最小改动迁移现有过程式代码，选 Functional API。两者共享同一底层运行时，且可在同一应用中并用 [1]。

**分支/并行可视化**

- Graph API 采用声明式方式定义节点、边与共享状态，形成可视化图结构；多个依赖不同条件的决策点使分支显式且易于可视化，并支持需要后续合并的并行执行路径 [1]。其显式状态管理便于跨组件共享与协调状态，可视化特性便于团队理解、记录和维护复杂工作流，并可按节点分工 [1]。
- Functional API 采用命令式方式，把 LangGraph 功能集成进标准过程式代码，适合线性工作流与简单分支逻辑 [1]。冻结文档未提供 Functional API 的图形式分支/并行可视化机制；这是本次可见材料的缺口，不能据此推断全部文档均无此内容。

**迁移现有过程式代码**

- Functional API 面向已有使用标准控制流（if/else、循环、函数调用）的代码，可用最少重构加入 LangGraph 功能 [1]。
- Graph API 的声明式节点/边/状态与可视化协作方式有助团队维护复杂工作流 [1]，但冻结文档未直接讨论从过程式代码迁移到 Graph API 的改造量；该维度无法据现有材料量化比较。

**取舍**

| 需求 | 更适用 | 依据 |
|---|---|---|
| 分支/并行可视化、团队协作 | Graph API | 显式分支、并行合并、可视化维护 [1] |
| 迁移现有过程式代码 | Functional API | 最少重构、标准控制流 [1] |

文档快速决策指南亦将“复杂工作流可视化”“条件分支”“需后续合并的并行路径”列为 Graph API 场景，将“对现有过程式代码做最小改动”列为 Functional API 场景 [1]。若团队同时有这两类需求，可考虑并用两 API [1]；但具体迁移成本与可视化效果需另行验证，冻结文档未给出量化指标。

## Sources

1. Choosing between Graph and Functional APIs — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/choosing-apis.mdx
