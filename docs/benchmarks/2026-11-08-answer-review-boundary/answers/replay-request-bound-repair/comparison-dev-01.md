# comparison-dev-01

Using only the frozen documentation, compare Graph API and Functional API for a team needing branching/parallel visualization versus migrating existing procedural code.

Component status: completed; error: None; new Provider calls: 1.

针对需要分支/并行可视化与迁移现有过程式代码的团队，冻结文档给出的对比是：

- 需要分支/并行可视化时选 Graph API。文档明确建议在需要“复杂工作流可视化”“带多个决策点的条件分支”“需要后续合并的并行执行路径”“团队协作且可视化有助于理解”时使用 Graph API[1]。Graph API 采用声明式方式定义节点、边和共享状态，形成可视化图结构；多决策点的分支会被显式呈现、易于可视化；并行运行多个操作再合并结果也能自然处理；其可视化特性便于团队理解、记录和维护复杂工作流[1]。
- 需要迁移现有过程式代码时选 Functional API。文档建议在希望“对现有过程式代码做最小改动”“使用标准控制流（if/else、循环、函数调用）”“快速原型、更少样板代码”“线性工作流与简单分支逻辑”时使用 Functional API[1]。Functional API 采用命令式方式，把 LangGraph 功能集成进标准过程式代码；当已有代码使用标准控制流、想以最小重构加入 LangGraph 功能时适用[1]。
- 两者共享同一底层运行时，可在同一应用中一起使用，但面向不同用例和开发偏好[1]。
- 文档还说明迁移方向：功能式工作流变复杂时可迁移到 Graph API；也存在从 Graph 到 Functional API 的迁移[1]。

结论：若团队的核心诉求是分支/并行的可视化与协作理解，Graph API 更匹配；若核心诉求是以最小改动把 LangGraph 能力接入现有过程式代码，Functional API 更匹配[1]。

Unresolved gaps: []
