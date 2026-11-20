# comparison-dev-01 / workflow

Using only the frozen documentation, compare Graph API and Functional API for a team needing branching/parallel visualization versus migrating existing procedural code.

Status: completed; answered: True; reason: None; model calls: 6; seconds: 29.826.

**结论：** 若团队的核心诉求是分支/并行可视化，选 Graph API；若核心诉求是以最小改动迁移现有过程式代码，选 Functional API。两者共享同一底层运行时，可在同一应用混用 [1]。

**分支/并行可视化**

- Graph API：采用声明式方法，定义节点、边与共享状态以形成可视化图结构；多决策点条件分支被显式表达且易于可视化；并行执行路径可在之后合并结果；可视化特性便于团队理解、记录和维护复杂工作流 [1]。
- Functional API：采用命令式方法，把 LangGraph 功能集成进标准过程式代码，支持 if/else、循环、函数调用等标准控制流，适用于带简单分支的线性工作流 [1]。可见材料未提及其独立可视化机制，故不能据此断言其支持或支持程度。

**迁移现有过程式代码**

- Functional API：明确面向“已有使用标准控制流的代码，以最小重构加入 LangGraph 功能” [1]。
- Graph API：采用声明式建图，可见材料未给出从过程式代码迁移的具体步骤或兼容性说明；不能推断其不可迁移，只表示本次材料未覆盖。

**取舍**

| 维度 | Graph API | Functional API |
|---|---|---|
| 分支/并行可视化 | 显式分支、并行后合并、可视化便于团队协作 [1] | 标准控制流、简单分支的线性流程；未述可视化 [1] |
| 迁移过程式代码 | 未给出迁移步骤 [1] | 最小改动、命令式集成 [1] |
| 状态管理 | 跨节点显式共享状态 [1] | 函数作用域状态，无需显式管理 [1] |
| 原型速度 | 未述 | 样板更少、适合快速原型 [1] |

文档还给出双向迁移入口：功能式工作流变复杂时可迁往 Graph API；图对简单线性流程过于复杂时可迁往 Functional API [1]。具体迁移步骤在可见摘录中被截断，无法确认细节。

**建议：** 以可视化与复杂分支/并行为首要目标时用 Graph API；以保留现有过程式结构、少改代码为首要目标时用 Functional API；两者可同应用混用，按模块选择 [1]。

## Sources

1. Choosing between Graph and Functional APIs — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/choosing-apis.mdx
