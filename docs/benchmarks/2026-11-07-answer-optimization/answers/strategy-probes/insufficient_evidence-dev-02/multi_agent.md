# insufficient_evidence-dev-02 / multi_agent

Using only the frozen documentation, using the API-choice guide alone, give the percentage latency improvement of Graph API over Functional API.

Status: partial; answered: False; reason: no_research_progress; model calls: 8; seconds: 24.917.

**无法给出该百分比。** 仅依据 API-choice guide [1]，文中没有给出 Graph API 相对 Functional API 的延迟改进百分比，也没有给出两者可用来计算百分比的延迟数值。

该指南只按使用场景和开发偏好区分两种 API：Graph API 适合复杂工作流可视化、显式状态管理、条件分支、并行路径合并和团队协作 [1]；Functional API 适合对现有过程式代码做最小改动、标准控制流、函数级状态、快速原型和线性工作流 [1]。文中没有基准、场景、实测或估计等延迟条件，因此无法计算或引用任何百分比。

缺口说明：这是本次可见材料不足，不能据此推断全部文档均无该数据；如需该指标，应查阅包含延迟测量或基准数据的其他文档。

## Sources

1. Choosing between Graph and Functional APIs — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/choosing-apis.mdx
