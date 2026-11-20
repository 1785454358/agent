# comparison-dev-01

Using only the frozen documentation, compare Graph API and Functional API for a team needing branching/parallel visualization versus migrating existing procedural code.

Component status: completed; error: None; new Provider calls: 1.

按冻结文档，团队若需要分支/并行可视化，应选 Graph API：它适合“复杂工作流可视化（用于调试和文档）”“带多个决策点的条件分支”“需要后续合并的并行执行路径”，以及“视觉表示有助于理解的团队协作”[1]。Graph API 采用声明式方法，通过定义节点、边和共享状态形成可视图结构；多个决策点的分支会被显式呈现、易于可视化，并行运行多个操作再合并结果也能自然处理[1]。若团队要迁移现有过程式代码，应选 Functional API：它适合“对现有过程式代码做最小改动”，采用命令式方法，把 LangGraph 功能集成进标准过程式代码，并支持标准控制流（if/else、循环、函数调用）[1]。文档还说明，当功能式工作流变复杂时可迁移到 Graph API，反向也可从 Graph 迁到 Functional API[1]。结论：分支/并行可视化优先 Graph API；迁移现有过程式代码优先 Functional API[1]。

Unresolved gaps: []
