# insufficient_evidence-dev-02 / plan_execute

Using only the frozen documentation, using the API-choice guide alone, give the percentage latency improvement of Graph API over Functional API.

Status: partial; answered: False; reason: insufficient_evidence; model calls: 6; seconds: 22.001.

无法给出该百分比：仅依据 API-choice 指南，原文没有提供 Graph API 与 Functional API 的任何延迟数据或延迟改进百分比 [1]。

指南只按使用场景和设计取向比较两者：Graph API 适合复杂工作流可视化、显式状态管理、条件分支、并行执行与团队协作；Functional API 适合对现有过程式代码做最小改动、标准控制流、函数级状态、快速原型和线性工作流 [1]。这些是适用场景描述，不是性能测量。

由于缺少两种 API 的延迟数值，也无法按“（Functional 延迟 − Graph 延迟）/ Functional 延迟”计算改进比例；原文同样没有给出可保留的测量条件 [1]。

该缺口仅表示本次可见的指南材料不足，不能据此断定全部文档或该领域没有相关数据。若要回答，需要指南中明确给出两 API 的延迟测量值及测量条件。

## Sources

1. Choosing between Graph and Functional APIs — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/choosing-apis.mdx
