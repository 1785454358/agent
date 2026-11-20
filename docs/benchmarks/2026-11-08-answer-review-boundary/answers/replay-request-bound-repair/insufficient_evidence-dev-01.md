# insufficient_evidence-dev-01

Using only the frozen documentation, from the persistence overview alone, provide production checkpoint database throughput, per-request cost and a recovery-time SLA. What can actually be concluded?

Component status: partial; error: None; new Provider calls: 1.

仅凭该持久化概览无法得出生产检查点数据库吞吐量、每请求成本或恢复时间SLA：文中没有给出任何吞吐量数值、单请求成本数值或恢复时间SLA指标[1]。概览只说明检查点用于短期、线程范围的记忆，包括对话连续性、人在回路、时间旅行和容错[1]；并指出生产环境应使用持久化检查点器，如PostgresSaver（PostgreSQL，支持异步）或SqliteSaver（本地文件存储，用于开发）[1]。它还提示长对话中检查点会累积，可能增加延迟和存储成本，并建议用定时任务删除超过N天的检查点[1]。因此可结论为：这些性能与成本指标在概览中未量化，只能确认存在延迟/存储成本风险及清理建议，无法给出具体吞吐、单价或SLA。

Unresolved gaps: ["provide production checkpoint database throughput, per-request cost and a recovery-time SLA"]
