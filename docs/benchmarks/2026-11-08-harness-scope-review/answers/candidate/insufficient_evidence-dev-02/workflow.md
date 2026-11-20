# insufficient_evidence-dev-02 / workflow

Using only the frozen documentation, using the API-choice guide alone, give the percentage latency improvement of Graph API over Functional API.

Status: completed; answered: False; reason: insufficient_evidence; model calls: 12; tools: 14; seconds: 32.349.

无法给出该百分比。仅依据所加载的 API-choice guide 可见原文，指南没有出现 Graph API 相对 Functional API 的延迟改进百分比，也没有任何延迟数值或可用于计算延迟改进的测量条件 [1]。

指南对两种 API 的比较维度是使用场景与开发偏好：Graph API 适合复杂工作流可视化、显式状态管理、条件分支、并行执行后合并、团队协作；Functional API 适合对现有过程式代码做最小改动、标准控制流、函数作用域状态、快速原型、线性流程 [1]。这些是适用场景取舍，不是性能数据。

因此，r1（具体百分比）与 r2（可据以计算的数据或条件）在本次可见材料中均为缺口；这仅表示当前可见的指南片段不足，不能推出完整文档或该领域没有相关数据。若要回答，需要指南中明确给出延迟测量方法、对比基准与结果，或给出可复算的输入；目前无法完成验证。

## Sources

1. Choosing between Graph and Functional APIs — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/choosing-apis.mdx
