# comparison-dev-01 / plan_execute

Using only the frozen documentation, compare Graph API and Functional API for a team needing branching/parallel visualization versus migrating existing procedural code.

Status: partial; answered: False; reason: max_replans_reached; model calls: 13; tools: 15; seconds: 58.371.

**结论：** 若团队的核心需求是分支/并行结构的可视化，文档明确指向 Graph API；若核心需求是以最小改动迁移现有过程式代码，文档明确指向 Functional API。两者共享同一底层运行时，可在同一应用中一起使用 [1]。

**分支/并行可视化**

| 维度 | Graph API | Functional API |
|---|---|---|
| 建模方式 | 声明式：定义节点、边与共享状态，形成可视化图结构 [1] | 命令式：把 LangGraph 功能集成进标准过程式代码 [1] |
| 条件分支 | 文档称其使多个决策点的分支显式且易于可视化，示例用 `add_conditional_edges` 建模 [1] | 用标准 Python 控制流（if/else）实现简单分支 [1] |
| 并行路径 | 文档称能自然处理并行执行并在之后合并结果，示例以 fetch_news、fetch_weather、fetch_stocks 多节点汇入 combine 节点体现 [1] | 文档定位其适用于线性工作流与简单分支逻辑，未描述多路并行汇合的可视化 [1] |
| 适用定位 | 复杂工作流可视化、条件分支、需后续合并的并行路径、团队协作可视化理解 [1] | 快速原型、线性工作流、简单分支 [1] |

因此，对“分支/并行可视化”这一维度，Graph API 是文档明确指向的选择；Functional API 的文档描述只覆盖简单分支，未给出并行汇合的可视化支持。

**迁移现有过程式代码**

Functional API 被明确描述为面向已有使用标准控制流的过程式代码，可在最小重构下加入 LangGraph 功能，示例强调对现有函数做最小改动 [1]。Graph API 一侧，本次可见材料未描述从过程式代码迁移到 Graph API 的步骤、需改写内容或注意事项——这是本次可见材料的缺口，不能据此推断全部文档没有相关说明。

**取舍与混用**

- 两类需求同时存在时，文档允许两者在同一应用中共用同一运行时 [1]，可考虑以 Graph API 承担需要可视化理解的分支/并行部分，以 Functional API 承接已有过程式代码。
- 该混用是文档所述的能力边界，具体拆分方式与迁移步骤属于建议，需按实际代码验证。

## Sources

1. Choosing between Graph and Functional APIs — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/choosing-apis.mdx
