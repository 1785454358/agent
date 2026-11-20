# insufficient_evidence-dev-02 / workflow

Using only the frozen documentation, using the API-choice guide alone, give the percentage latency improvement of Graph API over Functional API.

Status: completed; answered: False; reason: insufficient_evidence; model calls: 11; seconds: 27.895.

**无法给出该百分比。** 仅依据 API-choice guide [1]，原文没有给出 Graph API 相对 Functional API 的延迟改进百分比，也没有给出任何延迟数值或基准测试结果。因此该指标在本次可见材料中缺失，不能计算，也不能用常识补全。

原文只按使用场景比较两者：Graph API 适合复杂工作流可视化、显式状态管理、条件分支、并行执行后合并、团队协作 [1]；Functional API 适合对现有过程式代码做最小改动、标准控制流、函数作用域状态、快速原型、简单线性工作流 [1]。两者共享同一底层运行时 [1]，但指南未据此给出性能差异数据。

若要得到该百分比，需要补充包含两种 API 在同一任务、同一硬件与负载下的延迟测量（如均值或分位数）及测量方法的资料；这属于验证建议，不是原文结论。

## Sources

1. Choosing between Graph and Functional APIs — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/choosing-apis.mdx
