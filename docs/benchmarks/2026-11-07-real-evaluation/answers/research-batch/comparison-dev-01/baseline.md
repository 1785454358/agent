# comparison-dev-01 / baseline

Using only the frozen documentation, compare Graph API and Functional API for a team needing branching/parallel visualization versus migrating existing procedural code.

Status: completed; answered flag: True; response reason: None; model calls: 2; seconds: 11.793.

**结论：** 对“需要分支/并行可视化”的团队，选 Graph API；对“迁移现有过程式代码”的团队，选 Functional API。两者共享同一底层运行时，且可在同一应用中混用 [1]。

**按两个需求维度比较**

| 维度 | Graph API | Functional API |
|---|---|---|
| 分支/并行可视化 | 声明式定义节点、边与共享状态，形成可视化图结构；多决策点分支显式、易可视化 [1] | 命令式，融入标准过程式代码；适合线性流程与简单分支 [1] |
| 并行后合并 | 原生支持并行执行路径并在之后合并结果 [1] | 文档未给出并行合并的对应说明 |
| 迁移现有过程式代码 | 需改为节点/边/状态结构 | 最小改动即可为现有代码加上 LangGraph 特性，保留 if/else、循环、函数调用 [1] |
| 状态管理 | 显式共享状态，跨节点协调 [1] | 函数作用域状态，无需显式状态管理 [1] |
| 团队协作/文档 | 可视化便于团队理解、记录与维护复杂流程 [1] | 文档未给出对应优势 |

**取舍与条件**

- 分支/并行可视化优先：Graph API 把复杂决策树、并行处理与同步显式化，适合调试、文档和团队协作 [1]。
- 迁移优先：Functional API 用 `@task`/`@entrypoint` 包裹现有函数，主体仍是标准控制流，重构量小 [1]。
- 两者可混用：文档示例中 Functional 的 `data_processor` 结果可被 Graph 的节点调用 [1]。
- 迁移方向：功能流程变复杂时可迁到 Graph API；图对简单线性流程过度设计时可退回 Functional API [1]。

**注意：** 故障重试、超时等机制在 Graph 的 `add_node` 与 Functional 的 `@task`/`@entrypoint` 上均有对应参数 [2]，不构成两者取舍的决定因素；流式输出文档主要围绕编译后的图执行 [3]，未给出 Functional API 的对比说明。

## Sources

1. Choosing between Graph and Functional APIs — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/choosing-apis.mdx
2. Fault tolerance — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/fault-tolerance.mdx
3. Streaming — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/streaming.mdx
