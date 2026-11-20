# comparison-dev-01 / plan_execute

Using only the frozen documentation, compare Graph API and Functional API for a team needing branching/parallel visualization versus migrating existing procedural code.

Status: partial; answered: False; reason: max_replans_reached; model calls: 12; seconds: 58.761.

**结论：** 若团队的核心诉求是分支/并行可视化，选 Graph API；若核心诉求是以最小改动迁移现有过程式代码，选 Functional API。两者共享同一底层运行时，可在同一应用中并用 [1]。

| 维度 | Graph API | Functional API |
|---|---|---|
| 分支表达 | 采用声明式方法，定义节点、边与共享状态以构成可视化图结构；当工作流有多个依赖不同条件的决策点时，使分支显式、易可视化 [1] | 采用命令式方法，将 LangGraph 功能集成进标准过程式代码，适合标准控制流（if/else、循环、函数调用）与简单分支的线性工作流 [1] |
| 并行合并 | 需要并行运行多个操作再合并结果时，Graph API 自然处理；示例中 combine 节点等待所有并行操作完成 [1] | 原文未说明并行合并的表达方式 |
| 可视化 | 图的可视化特性便于团队理解、记录、维护复杂工作流，并支持成员分工处理不同节点 [1] | 原文未提可视化能力 |
| 迁移现有过程式代码 | 原文未提供迁移说明、步骤或兼容性限制（缺口） | 适用于已有使用标准控制流的代码，只需最小重构即可添加 LangGraph 功能 [1] |

**取舍条件：** 快速决策指南直接按场景给出建议——需要复杂工作流可视化（用于调试与文档）、跨多节点的显式状态管理、多决策点的条件分支、需后续合并的并行执行路径或团队协作时用 Graph API；希望最小改动现有过程式代码、使用标准控制流、函数级状态、快速原型或简单分支线性工作流时用 Functional API [1]。

**缺口说明：** 本次可见材料未覆盖“过程式代码迁移到 Graph API”的步骤与限制，故无法据此评估该路径的迁移成本；这不代表全部文档均无此内容。原文另提到可从 Functional 迁移到 Graph API，但摘录未给出具体步骤 [1]，同样无法展开。

## Sources

1. Choosing between Graph and Functional APIs — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/choosing-apis.mdx
