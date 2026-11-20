# insufficient_evidence-dev-01 / baseline

Using only the frozen documentation, from the persistence overview alone, provide production checkpoint database throughput, per-request cost and a recovery-time SLA. What can actually be concluded?

Status: completed; answered flag: True; response reason: None; model calls: 2; seconds: 9.940.

**结论：仅凭这份持久化概览，无法给出生产环境 checkpoint 数据库吞吐、每请求成本或恢复时间 SLA 的具体数值；原文没有提供任何此类测量或承诺。**

能确认的只有机制层面的事实：

- 每个 super-step 边界创建 checkpoint，节点级写入先落到 `checkpoint_writes` 表，super-step 完成后提交完整状态快照 [1]。
- 默认每个 super-step 写入所有状态通道的完整值，长线程可能造成显著存储增长 [1]；`DeltaChannel` 可把 checkpoint blob 降为每步 O(1) [1]。
- 生产可用后端包括 Postgres、MongoDB、Redis、Azure Cosmos DB 等，但原文只称“适合生产”，未给性能或成本数据 [1]。
- 恢复只能从 checkpoint（super-step 边界）继续；同一 super-step 内失败节点的已完成写入可复用，无需重跑 [1]。

因此：

| 询问项 | 可结论 |
|---|---|
| 吞吐 | 无数据；只能推断受 super-step 频率、状态大小、后端查询能力影响 [1] |
| 每请求成本 | 无数据；只能推断与每步全量写入及存储增长相关，`DeltaChannel` 可降低 blob 体积 [1] |
| 恢复时间 SLA | 无承诺；原文只说明可恢复及恢复粒度 [1] |

要得到这些指标，需补充基准测试：目标后端、状态通道大小、super-step 频率、并发线程数、`get_tuple`/祖先链查询次数 [1]，以及恢复时重放写入的实测耗时。这些是验证建议，不是原文事实。

## Sources

1. Checkpointers — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/checkpointers.mdx
