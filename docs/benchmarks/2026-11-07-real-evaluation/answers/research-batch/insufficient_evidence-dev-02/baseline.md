# insufficient_evidence-dev-02 / baseline

Using only the frozen documentation, using the API-choice guide alone, give the percentage latency improvement of Graph API over Functional API.

Status: partial; answered flag: False; response reason: answer_review_incomplete; model calls: 2; seconds: 6.233.

无法给出该百分比。仅依据 API-choice 指南 [1]，全文没有提供 Graph API 与 Functional API 的延迟测量值、基准测试或任何性能对比数字；该指南只按使用场景区分两者，例如 Graph API 适合复杂分支、并行与显式状态，Functional API 适合线性流程与快速原型 [1]。因此“Graph API 比 Functional API 快多少”在指定来源中不可得，任何百分比都会是编造。

若需该指标，建议另行核查：是否有同一工作负载下的基准测试、测量的是端到端还是单步延迟、是否启用检查点等配置一致。这些属于验证建议，不是原文事实。

## Sources

1. Choosing between Graph and Functional APIs — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/choosing-apis.mdx
