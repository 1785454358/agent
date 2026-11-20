# insufficient_evidence-dev-02 / multi_agent

Using only the frozen documentation, using the API-choice guide alone, give the percentage latency improvement of Graph API over Functional API.

Status: partial; answered: False; reason: no_research_progress; model calls: 8; tools: 5; seconds: 22.573.

无法给出该百分比。仅依据 API-choice 指南 [1]，可见原文只比较两种 API 的适用场景与设计偏好（如 Graph API 适合复杂分支、并行与显式状态管理，Functional API 适合线性流程与快速原型），未提供任何延迟测量、基准数据或 Graph API 相对 Functional API 的百分比延迟改进 [1]。

因此该指标在本次可见材料中缺失，不能以常识或推断补全。若要得到该数值，需补充包含两种 API 在同一任务、同一硬件与负载下的延迟测量（如均值/分位数、样本量与测量方法）的文档或基准结果；这属于验证建议，并非原文事实。

## Sources

1. Choosing between Graph and Functional APIs — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/choosing-apis.mdx
