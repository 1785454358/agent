# comparison-dev-01 / workflow

Using only the frozen documentation, compare Graph API and Functional API for a team needing branching/parallel visualization versus migrating existing procedural code.

Status: completed; answered: False; reason: insufficient_evidence; model calls: 13; tools: 18; seconds: 60.570.

**结论：若团队首要需求是分支/并行可视化，选 Graph API；若首要需求是以最小改动迁移现有过程式代码，选 Functional API。** 两者共享同一底层运行时，可在同一应用混用，但面向不同用例与开发偏好 [1]。

| 维度 | Graph API | Functional API |
|---|---|---|
| 构建方式 | 声明式：定义节点、边与共享状态，形成可视化图结构 [1] | 命令式：把 LangGraph 特性集成进标准过程式代码 [1] |
| 分支可视化 | 多决策点条件分支被显式表达、易于可视化，示例用 `add_conditional_edges` [1] | 文档仅称适合“带简单分支的线性工作流”，未说明其分支/并行可视化的支持方式、条件或限制 [1] |
| 并行可视化 | 可并行运行多个操作再合并，示例中 `combine` 节点等待所有并行操作完成后才继续 [1] | 同上，未说明并行可视化支持 [1] |
| 迁移现有过程式代码 | 文档未说明迁移路径、要求或限制 | 可在最小重构下为使用标准控制流的现有代码加入 LangGraph 特性，示例保留普通 if/else 并以 `task`/`entrypoint` 包装函数 [1] |
| 状态 | 显式共享状态，便于跨组件协调 [1] | 函数作用域状态，无需显式状态管理 [1] |
| 团队协作 | 可视化便于理解、记录、维护复杂工作流，支持按节点分工 [1] | 未就团队可视化协作作说明 |

**取舍条件。** 快速决策指南建议：需要复杂工作流可视化、显式共享状态、多决策点条件分支、需后续合并的并行路径或团队协作时用 Graph API；希望最小改动现有过程式代码、使用标准控制流、函数作用域状态、快速原型或带简单分支的线性工作流时用 Functional API [1]。

**缺口（仅指本次可见材料不足，不能推出全部文档无答案）。** ① Functional API 对分支/并行可视化的支持方式、条件与限制：原文只给出“线性工作流+简单分支”的适用描述，未展开机制 [1]。② 从现有过程式代码迁移到 Graph API 的路径、要求与限制：原文未说明。若需据此决策，建议补充核查这两处的专门文档或示例，而非按常识补全。

**实际意义。** 若团队同时承担两类任务，可先以 Graph API 承载需要可视化审查的分支/并行主干，再在节点内或独立入口复用 Functional API 包装的既有过程式函数；此组合依据“共享运行时、可同应用混用” [1]，但具体混用边界原文未展开。

## Sources

1. Choosing between Graph and Functional APIs — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/choosing-apis.mdx
