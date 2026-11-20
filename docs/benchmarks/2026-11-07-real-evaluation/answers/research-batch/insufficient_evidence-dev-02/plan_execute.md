# insufficient_evidence-dev-02 / plan_execute

Using only the frozen documentation, using the API-choice guide alone, give the percentage latency improvement of Graph API over Functional API.

Status: partial; answered flag: False; response reason: no_research_progress; model calls: 10; seconds: 29.411.

无法给出该百分比。仅依据 API-choice 指南 [1]，原文没有出现 Graph API 相对 Functional API 的延迟改进百分比、数值或单位，也没有对两者延迟作比较，因此既不能直接引用，也不能据此推算。

指南实际比较的是适用场景：Graph API 适合复杂工作流可视化、显式状态管理、条件分支、并行执行后合并及团队协作 [1]；Functional API 适合对现有过程式代码做最小改动、标准控制流、函数作用域状态、快速原型和简单线性流程 [1]。这些是选型建议，不是性能测量结论。

缺口说明：本次可见材料未提供测量口径、比较基准、工作负载、版本或环境，故无法完成验证；这仅表示当前可见材料不足，不能推出全部文档均无该数据。若要得到百分比，需查阅包含基准测试或延迟测量的文档，并核对上述测量条件。

## Sources

1. Choosing between Graph and Functional APIs — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/choosing-apis.mdx
