# comparison-dev-01 / plan_execute

Using only the frozen documentation, compare Graph API and Functional API for a team needing branching/parallel visualization versus migrating existing procedural code.

Status: completed; answered: True; reason: None; model calls: 6; tools: 7; seconds: 30.224.

**结论：** 若团队的核心诉求是分支/并行可视化与协作维护，选 **Graph API**；若核心诉求是以最小改动迁移现有过程式代码，选 **Functional API**。两者共享同一底层运行时，也可在同一应用混用 [1]。

| 维度 | Graph API | Functional API |
|---|---|---|
| 构建方式 | 声明式：定义节点、边、共享状态，形成可视化图结构 [1] | 命令式：把 LangGraph 特性集成进标准过程式代码 [1] |
| 分支/并行可视化 | 多决策点的分支显式且易可视化；并行执行后合并结果可自然处理 [1] | 面向标准控制流（if/else、循环、函数调用）与简单分支的线性工作流 [1] |
| 状态管理 | 显式共享状态，跨多个节点协调 [1] | 函数作用域状态，无需显式状态管理 [1] |
| 迁移现有代码 | 需改为图结构 | 最小重构即可加入 LangGraph 特性 [1] |
| 团队协作 | 可视化便于理解、记录和维护复杂工作流 [1] | 文档未给出对应协作/可视化优势 |

**取舍条件：**
- 分支/并行可视化优先：Graph API 的收益来自“分支显式化”和“并行后合并”这两类结构 [1]；代价是需按节点/边/共享状态重新组织代码。
- 迁移过程式代码优先：Functional API 用 `@task`、`@entrypoint` 包装现有函数，保留标准 Python 控制流，改动最小 [1]。
- 两者可共存：同一应用可同时使用两种 API [1]；文档还给出 Functional→Graph 与 Graph→Functional 的双向迁移路径 [1]，因此可先按当前主诉求选型，后续随复杂度变化迁移。

**适用场景：** 复杂决策树、多数据源并行后汇总、需要团队共同维护文档化流程 → Graph API [1]；已有过程式代码、线性流程、快速原型 → Functional API [1]。

**缺口说明：** 冻结文档未提供性能、成本或迁移工作量的量化指标，无法据此做数值比较；上述比较仅基于文档列出的适用条件 [1]。

## Sources

1. Choosing between Graph and Functional APIs — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/choosing-apis.mdx
