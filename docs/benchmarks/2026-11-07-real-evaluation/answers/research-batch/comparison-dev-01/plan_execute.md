# comparison-dev-01 / plan_execute

Using only the frozen documentation, compare Graph API and Functional API for a team needing branching/parallel visualization versus migrating existing procedural code.

Status: partial; answered flag: False; response reason: max_replans_reached; model calls: 12; seconds: 53.864.

**结论：分支/并行可视化选 Graph API；迁移现有过程式代码选 Functional API。** 文档的快速决策指南正是按这两个场景分别推荐的 [1]。

| 维度 | Graph API | Functional API |
|---|---|---|
| 分支/并行 | 多决策点条件分支显式且易可视化；并行执行后合并结果可自然处理 [1] | 适合带简单分支的线性工作流，标准 if/else、循环、函数调用 [1] |
| 可视化 | 声明式定义节点、边与共享状态，形成可视化图结构；便于团队理解、记录和维护复杂工作流 [1] | 命令式，把 LangGraph 功能集成进过程式代码；文档未描述其图可视化能力 [1] |
| 迁移现有代码 | 文档未提供从过程式代码迁移到 Graph API 的方式、前提或注意事项（本次可见材料缺口） | 以最小重构给现有过程式代码加入 LangGraph 功能，保留标准控制流 [1] |
| 状态 | 跨节点共享的显式状态管理 [1] | 函数作用域状态，无需显式状态管理 [1] |

**取舍条件：** 若团队核心诉求是让多个决策点和需后续合并的并行路径“看得见”、便于协作与文档化，Graph API 更匹配 [1]。若核心诉求是尽量少改现有过程式代码、快速原型、工作流以线性为主仅含简单分支，Functional API 更匹配 [1]。两者共享同一底层运行时，可在同一应用中并用 [1]。

**缺口说明：** 关于“从现有过程式代码迁移到 Graph API”的具体迁移方式、前提与注意事项，本次可见材料未给出，不能据此推断全部文档无答案；如需该维度，应补充核查 Graph API 文档中的迁移章节。另，文档未对两 API 的可视化能力做并列量化比较，上表“可视化”一行的 Functional 侧仅为“文档未描述”，非否定其能力。

## Sources

1. Choosing between Graph and Functional APIs — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/choosing-apis.mdx
