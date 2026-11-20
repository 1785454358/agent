# comparison-dev-01 / workflow

Using only the frozen documentation, compare Graph API and Functional API for a team needing branching/parallel visualization versus migrating existing procedural code.

Status: completed; answered: True; reason: None; model calls: 6; tools: 8; seconds: 30.984.

**结论**：若团队的核心诉求是分支/并行可视化与协作理解，选 Graph API；若核心诉求是以最小改动迁移现有过程式代码，选 Functional API。两者不是“谁更强”，而是按场景取舍 [1]。

| 维度 | Graph API | Functional API |
|---|---|---|
| 定义方式 | 声明式：定义节点、边、共享状态，形成可视化图结构 [1] | 命令式：把 LangGraph 功能集成进标准过程式代码 [1] |
| 分支/并行 | 多决策点分支显式且易可视化；并行执行后合并结果可自然处理 [1] | 适合线性工作流与简单分支逻辑 [1] |
| 状态 | 显式共享状态，跨多个节点协调 [1] | 函数作用域状态，无需显式状态管理 [1] |
| 团队协作 | 可视化便于理解、记录和维护复杂工作流 [1] | 文档未给出面向可视化的协作优势 |
| 迁移现有代码 | 文档未给出低改动迁移优势 | 最小代码改动，保留 if/else、循环、函数调用等标准控制流 [1] |
| 原型速度 | 文档未给出 | 样板更少，适合快速原型 [1] |

**分支/并行可视化场景**：Graph API 的适用条件正是“复杂工作流可视化、显式状态管理、条件分支、需后续合并的并行路径、可视化辅助团队理解” [1]。其声明式图结构使多个条件分支点显式表达，并行运行多个操作再合并也能自然处理 [1]。因此该团队应优先 Graph API。

**迁移现有过程式代码场景**：Functional API 的适用条件是“对现有过程式代码做最小改动、使用标准控制流、函数作用域状态、快速原型、带简单分支的线性工作流” [1]。文档示例在现有函数上做最小改动，并用标准 Python 的 if/else 组织流程 [1]。因此该团队应优先 Functional API。

**取舍与边界**：若同一团队同时有这两个诉求，文档只给出按需求选 API 的决策指南，并指出功能式工作流变复杂时可迁移到 Graph API、图对简单线性流程过于复杂时可迁回 Functional API [1]；未给出两套 API 并行混用的具体方案，这属于本次可见材料未覆盖的部分。

**建议**：以“是否需要把分支与并行路径作为可视化结构供团队审阅”为主判据；是则 Graph，否则以迁移成本为主判据选 Functional [1]。

## Sources

1. Choosing between Graph and Functional APIs — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/choosing-apis.mdx
