# insufficient_evidence-dev-02 / workflow

Using only the frozen documentation, using the API-choice guide alone, give the percentage latency improvement of Graph API over Functional API.

Status: completed; answered: False; reason: insufficient_evidence; model calls: 11; tools: 15; seconds: 30.785.

**结论：无法给出该百分比。** 仅依据所加载的 API-choice guide 可见原文，其中没有出现 Graph API 相对 Functional API 的任何延迟改进百分比，也没有任何延迟对比数值 [1]。因此不能给出具体数字，也不能用常识或其他资料补全。

**缺口说明**

- 该指南只按使用场景区分两种 API：Graph API 适合复杂可视化、显式状态、条件分支、并行合并与团队协作；Functional API 适合最小改动、标准控制流、函数级状态、快速原型与线性流程 [1]。
- 原文未陈述延迟对比，因而也没有基准环境、版本、是否实测等限定说明 [1]。

**适用条件**：上述“无数据”结论仅限本次可见的该指南文本，不能推出全部冻结文档均无答案。若要得到百分比，需核查该指南是否另有未加载段落，或确认其他文档是否含基准测试；这属于验证建议，不是原文事实。

## Sources

1. Choosing between Graph and Functional APIs — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/choosing-apis.mdx
