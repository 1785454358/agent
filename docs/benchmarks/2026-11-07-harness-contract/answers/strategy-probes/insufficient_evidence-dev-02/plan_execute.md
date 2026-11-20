# insufficient_evidence-dev-02 / plan_execute

Using only the frozen documentation, using the API-choice guide alone, give the percentage latency improvement of Graph API over Functional API.

Status: partial; answered: False; reason: no_research_progress; model calls: 10; tools: 11; seconds: 26.969.

无法给出该百分比。仅依据 API-choice 指南 [1]，原文只比较两种 API 的适用场景与设计偏好，未提供 Graph API 相对 Functional API 的延迟数据或百分比。

指南中的取舍是：Graph API 适合复杂工作流可视化、显式状态管理、条件分支、并行执行后合并及团队协作 [1]；Functional API 适合对现有过程式代码做最小改动、标准控制流、函数作用域状态、快速原型和简单线性流程 [1]。这些是适用性描述，不是性能测量。

因此，该延迟改进指标在本次可见材料中缺失；不能由“共享同一底层运行时” [1] 推出两者延迟相同，也不能用场景偏好补出百分比。若要得到该数值，需有同一任务、同一硬件与负载下的对照基准及测量方法，但当前材料未提供这些输入。

## Sources

1. Choosing between Graph and Functional APIs — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/choosing-apis.mdx
