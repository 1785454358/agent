# comparison-dev-01 / multi_agent

Using only the frozen documentation, compare Graph API and Functional API for a team needing branching/parallel visualization versus migrating existing procedural code.

Status: partial; answered: False; reason: max_follow_ups_reached; model calls: 12; seconds: 59.169.

**结论**：若团队首要目标是分支/并行可视化，选 Graph API；若首要目标是以最小改动迁移现有过程式代码，选 Functional API。文档对这两个场景分别给出直接指引，但未给出“同时满足两者”的单一推荐 [1]。

**分支/并行可视化：Graph API 占优**

- Graph API 是声明式：定义节点、边与共享状态，形成可视化图结构 [1]。
- 多个决策点的条件分支被显式化、易可视化 [1]。
- 并行执行后合并结果由 Graph API 自然处理 [1]。
- 适用条件：复杂工作流可视化、显式状态管理、多决策点条件分支、需后续合并的并行路径、可视化辅助团队协作 [1]。

**迁移现有过程式代码：Functional API 占优**

- Functional API 是命令式，把 LangGraph 功能集成进标准过程式代码 [1]。
- 适用条件：对现有代码最小改动、标准控制流（if/else、循环、函数调用）、函数作用域状态、快速原型、带简单分支的线性工作流 [1]。
- 文档示例展示对现有函数做最小改动即可接入 [1]。

**对比表**

| 维度 | Graph API | Functional API |
|---|---|---|
| 风格 | 声明式（节点/边/共享状态）[1] | 命令式（标准过程式代码）[1] |
| 分支可视化 | 显式、易可视化 [1] | 简单分支/线性流程 [1] |
| 并行合并 | 自然支持 [1] | 文档未作并行合并的明确说明 |
| 迁移成本 | 文档未说明 | 最小改动 [1] |

**取舍**

- 可视化优先：Graph API 的分支与并行结构直接对应图，便于调试与文档化 [1]。
- 迁移优先：Functional API 保留原有控制流，重构量小 [1]。
- 两者共享同一底层运行时，可在同一应用中并用 [1]；因此可按模块分工，而非全项目二选一。

**缺口**

本次可见材料未提供从现有过程式代码迁移到 Graph API 的步骤、兼容性或限制说明（r4 缺失）；也未说明 Functional API 在并行执行与合并上的具体行为。上述缺口仅表示当前材料不足，不能推断全部文档无相关内容。

**建议（基于上述证据的条件性推断）**：若团队既要可视化又要迁移，可先用 Functional API 低成本接入现有代码，再对分支/并行密集的部分逐步改用 Graph API；该路径的可行性依赖两者可并用这一表述 [1]，具体迁移步骤需另行核查文档。

## Sources

1. Choosing between Graph and Functional APIs — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/choosing-apis.mdx
