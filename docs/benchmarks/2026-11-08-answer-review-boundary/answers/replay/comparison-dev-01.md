# comparison-dev-01

Using only the frozen documentation, compare Graph API and Functional API for a team needing branching/parallel visualization versus migrating existing procedural code.

Component status: partial; error: None; new Provider calls: 1.

**结论：** 若团队核心需求是分支/并行结构的可视化与协作，选 Graph API；若核心需求是以最小改动迁移现有过程式代码，选 Functional API。两者共享同一底层运行时，可在同一应用中并用 [1]。

**按两个维度比较**

| 维度 | Graph API | Functional API |
|---|---|---|
| 分支/并行可视化 | 采用声明式方法，定义节点、边与共享状态，形成可视化图结构；多个决策点的分支显式且易可视化；并行执行后合并结果可自然处理；可视化便于团队理解、记录和维护复杂工作流 [1] | 采用命令式方法，集成进标准过程式代码；适用标准控制流（if/else、循环、函数调用）与“带简单分支逻辑的线性工作流” [1] |
| 迁移现有过程式代码 | 可见材料未提及迁移路径或兼容性注意事项 [1] | 明确适合“对现有过程式代码做最小改动” [1]；但未给出具体迁移步骤或兼容性注意事项 [1] |

**取舍与条件**

- 分支/并行可视化优先：Graph API 的选用理由包括复杂工作流可视化（调试与文档）、显式状态管理、条件分支、需后续合并的并行路径、以及视觉表示有助于理解的团队协作 [1]。
- 过程式代码迁移优先：Functional API 的选用理由包括最小代码改动、标准控制流、函数作用域状态、快速原型、简单分支的线性工作流 [1]。
- 两者并非互斥：共享运行时且可同应用并用，团队可按工作流部分分别采用 [1]。

**缺口说明（仅限本次可见材料）**

- Functional API 的分支/并行“可视化”能力：可见材料未作说明 [1]，不能据此推断其不支持。
- Graph API 的迁移路径与兼容性：可见材料未提及 [1]。
- Functional API 迁移的具体步骤与注意事项：仅有“最小改动”的定位，未展开 [1]。
- 可见材料含“From Functional to Graph API”与“From Graph to Functional API”小节标题 [1]，但摘录未含其正文，故无法给出具体迁移方法；需查阅对应小节原文核实。

Unresolved gaps: ["Functional API 是否支持分支/并行可视化，可见材料无依据", "Graph API 从过程式代码迁移的具体路径与兼容性，可见材料无依据", "两个迁移小节正文缺失，具体迁移方法无法给出"]
