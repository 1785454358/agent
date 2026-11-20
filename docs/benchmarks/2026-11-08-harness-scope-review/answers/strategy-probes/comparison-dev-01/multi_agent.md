# comparison-dev-01 / multi_agent

Using only the frozen documentation, compare Graph API and Functional API for a team needing branching/parallel visualization versus migrating existing procedural code.

Status: completed; answered: True; reason: None; model calls: 5; tools: 7; seconds: 34.565.

**结论**：若团队的核心诉求是分支/并行可视化，选 Graph API；若核心诉求是以最小改动迁移现有过程式代码，选 Functional API。冻结文档分别列出了两类 API 的适用场景，但未就这两个场景作直接对比或明确推荐 [1]。

**分支/并行可视化**

- Graph API：文档称其适合“复杂工作流可视化”“带多个决策点的条件分支”“需要后续合并的并行执行路径”，并称可视化特性便于团队理解、记录和维护复杂工作流 [1]。机制是声明式：定义节点、边和共享状态；示例用 `StateGraph` 添加节点，并以 `add_conditional_edges` 配合 `should_continue` 函数呈现决策路径 [1]。并行部分文档称其“自然处理”多操作并行后合并结果，并给出 `fetch_news`/`fetchStocks` 汇入 `combineData` 的示例 [1]。
- Functional API：文档仅将其适用场景列为“带简单分支的线性工作流”，未给出分支/并行可视化的具体机制或示例 [1]。

**迁移现有过程式代码**

- Functional API：文档称其采用命令式方法，把 LangGraph 功能集成进标准过程式代码，适合“以最小重构”为已有标准控制流代码加入 LangGraph 功能，并支持 if/else、循环、函数调用与函数作用域状态 [1]。
- Graph API：文档说明其声明式节点/边/状态结构及条件边示例，但未直接讨论迁移现有过程式代码的步骤或限制 [1]。

**取舍与条件**

- 两场景都重要时，文档未给统一推荐 [1]；可先按主诉求选型，并注意两 API 共享同一运行时、可在同一应用混用 [1]。
- 文档提到 Functional 工作流变复杂时可迁移到 Graph API，Graph 对简单线性流程过于复杂时可转向 Functional [1]；这是迁移方向说明，不是针对本问题的对比结论。
- 文档未提供两 API 在可视化质量、迁移工作量上的量化指标，无法据此做成本比较；需自行以实际代码与图结构验证。

## Sources

1. Choosing between Graph and Functional APIs — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/choosing-apis.mdx
