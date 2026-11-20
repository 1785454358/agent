# insufficient_evidence-dev-02 / workflow

Using only the frozen documentation, using the API-choice guide alone, give the percentage latency improvement of Graph API over Functional API.

Status: completed; answered flag: False; response reason: insufficient_evidence; model calls: 11; seconds: 30.767.

无法给出该百分比：在本次可见的 API-choice guide 原文中，没有出现 Graph API 相对 Functional API 的延迟改进百分比，也没有任何延迟数值或延迟差异的定性表述 [1]。该指南只按使用场景比较两套 API，例如 Graph API 适合复杂工作流可视化、显式状态管理、条件分支、并行执行与团队协作，Functional API 适合少量改动现有过程式代码、标准控制流、函数作用域状态、快速原型与线性工作流 [1]。

因此，问题所问的“百分比延迟改进”属于本次材料缺口，不能由现有原文推出，也不应借用常识补全。若要得到该指标，需要补充明确给出测量口径（如端到端或单节点延迟、负载与硬件条件）及对比数据的文档页面；这仅是核查建议，不是原文结论。

## Sources

1. Choosing between Graph and Functional APIs — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/choosing-apis.mdx
