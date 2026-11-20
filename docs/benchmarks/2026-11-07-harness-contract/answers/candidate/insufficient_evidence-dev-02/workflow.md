# insufficient_evidence-dev-02 / workflow

Using only the frozen documentation, using the API-choice guide alone, give the percentage latency improvement of Graph API over Functional API.

Status: completed; answered: False; reason: insufficient_evidence; model calls: 11; tools: 12; seconds: 29.717.

无法给出该百分比。仅依据 API-choice guide 的可见原文，该指南只按适用场景与开发偏好比较 Graph API 和 Functional API，未提供任何延迟数据或 Graph API 相对 Functional API 的延迟改进百分比 [1]。

原文能确认的是：两者共享同一底层运行时，可混用，但面向不同用例 [1]；Graph API 适合复杂工作流可视化、显式共享状态、条件分支、并行路径合并和团队协作 [1]；Functional API 适合对现有过程式代码做最小改动、标准控制流、函数级状态、快速原型和简单线性流程 [1]。这些是适用性取舍，不是性能结论。

因此，若需要该百分比，应补充包含两种 API 在同一任务、同一硬件与负载下的延迟测量资料；当前可见材料不足以计算或核验该指标。

## Sources

1. Choosing between Graph and Functional APIs — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/choosing-apis.mdx
