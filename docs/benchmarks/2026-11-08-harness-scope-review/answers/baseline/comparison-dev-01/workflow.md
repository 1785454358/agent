# comparison-dev-01 / workflow

Using only the frozen documentation, compare Graph API and Functional API for a team needing branching/parallel visualization versus migrating existing procedural code.

Status: partial; answered: False; reason: answer_review_incomplete; model calls: 6; tools: 11; seconds: 34.251.

**结论：** 若团队的核心需求是分支/并行结构的可视化与协作，选 Graph API；若核心需求是以最小改动迁移现有过程式代码，选 Functional API。两者共享同一底层运行时，可在同一应用中并用 [1]。

**按两个维度比较**

| 维度 | Graph API | Functional API |
|---|---|---|
| 分支/并行可视化 | 采用声明式方法，定义节点、边与共享状态以形成可视化图结构；多个决策点的分支显式且易可视化；并行执行后合并结果可自然处理；可视化便于团队理解、记录和维护复杂工作流 [1] | 采用命令式方法，将 LangGraph 功能集成进标准过程式代码；适用标准控制流（if/else、循环、函数调用）与“带简单分支逻辑的线性工作流” [1] |
| 迁移现有过程式代码 | 文档未提及迁移路径或兼容性注意事项 [1] | 明确适合“对现有过程式代码做最小改动”地加入 LangGraph 功能 [1]；但未给出具体迁移步骤或兼容性注意事项 [1] |

**取舍与条件**

- 分支/并行可视化优先：Graph API 的选用理由包括复杂工作流可视化（调试与文档）、显式状态管理、条件分支、需后续合并的并行路径、以及视觉表示有助于理解的团队协作 [1]。
- 过程式代码迁移优先：Functional API 的选用理由包括最小代码改动、标准控制流、函数作用域状态、快速原型、简单分支的线性工作流 [1]。
- 两者并非互斥：共享运行时且可同应用并用，团队可按工作流部分分别采用 [1]。

**缺口说明（仅限本次可见材料）**

- Functional API 的分支/并行“可视化”能力：文档未作说明 [1]，不能据此推断其不支持。
- Graph API 的迁移路径与兼容性：文档未提及 [1]。
- Functional API 迁移的具体步骤与注意事项：文档仅有“最小改动”的定位，未展开 [1]。
- 文档提到 Functional→Graph 与 Graph→Functional 的迁移小节标题 [1]，但可见摘录未含其正文，故无法给出具体迁移方法；需查阅对应小节原文核实。

## Sources

1. Choosing between Graph and Functional APIs — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/choosing-apis.mdx
