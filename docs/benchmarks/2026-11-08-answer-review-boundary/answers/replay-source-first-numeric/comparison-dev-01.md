# comparison-dev-01

Using only the frozen documentation, compare Graph API and Functional API for a team needing branching/parallel visualization versus migrating existing procedural code.

Component status: completed; error: None; new Provider calls: 1.

结论：若团队的核心需求是分支/并行流程的可视化，应选 Graph API；若核心需求是尽量少改动地迁移现有过程式代码，应选 Functional API。两者共享同一底层运行时，且可在同一应用中混用[1]。

面向“分支/并行可视化”的团队：Graph API 适用于需要复杂工作流可视化以便调试和文档化、带多个决策点的条件分支、需要后续合并的并行执行路径，以及视觉表示有助于理解的团队协作[1]。它采用声明式方式定义节点、边和共享状态，形成可视化图结构；多决策点分支会被显式呈现并易于可视化；并行运行多个操作再合并结果可由它自然处理；其可视化特性也便于团队理解、记录和维护复杂工作流[1]。

面向“迁移现有过程式代码”的团队：Functional API 适用于对现有过程式代码做最小代码改动、使用标准控制流（if/else、循环、函数调用）、无需显式状态管理的函数作用域状态、少样板代码的快速原型，以及带简单分支逻辑的线性工作流[1]。它采用命令式方式，把 LangGraph 功能集成进标准过程式代码；当已有代码使用标准控制流、又希望以最少重构加入 LangGraph 功能时适用[1]。

选择口径：需要显式控制工作流结构、复杂分支、并行处理或团队协作收益时选 Graph API；希望以最小改动给现有代码加入 LangGraph 功能、工作流简单线性或需要快速原型时选 Functional API[1]。此外，功能工作流变复杂后可从 Functional 迁移到 Graph API[1]。

Unresolved gaps: []
