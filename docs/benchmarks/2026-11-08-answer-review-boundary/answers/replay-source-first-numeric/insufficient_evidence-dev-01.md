# insufficient_evidence-dev-01

Using only the frozen documentation, from the persistence overview alone, provide production checkpoint database throughput, per-request cost and a recovery-time SLA. What can actually be concluded?

Component status: partial; error: None; new Provider calls: 1.

结论：仅凭这份持久化概览，无法给出生产环境的检查点数据库吞吐量、单请求成本或恢复时间 SLA；原文没有提供任何可量化的性能、成本或恢复时限指标[1]。

可以得出的内容：
- 持久化让 LangGraph 应用在单次图运行之外保留信息，适用于继续对话、中断后恢复、故障恢复和跨交互记忆[1]。
- 检查点器（Checkpointer）把线程的图状态保存为检查点，用于短期、线程范围内的记忆，包括对话连续性、human-in-the-loop、时间旅行和容错；Store 保存图状态之外的应用定义数据，用于长期、跨线程记忆[1]。
- 生产环境应使用持久化检查点器：PostgresSaver（PostgreSQL，支持异步）或 SqliteSaver（本地文件存储，用于开发）；MemorySaver 和 InMemorySaver 把检查点存在 RAM，进程重启后全部丢失[1]。
- 长对话中检查点会累积，可能增加延迟和存储成本；原文建议用 PostgresSaver.setup() 创建带索引的表，并考虑用 cron 任务删除超过 N 天的检查点[1]。
- 使用 Agent Server 时无需手动实现或配置检查点器或 Store，服务器在后台处理持久化基础设施[1]。

因此，原文只能支持“存在延迟与存储成本风险、需要清理旧检查点、生产应选持久化后端”这类定性结论，不能据此推导吞吐量、每请求成本或恢复时间 SLA 的具体数值[1]。

Unresolved gaps: ["生产检查点数据库吞吐量：原文无依据，不能量化[1]", "每请求成本：原文无依据，不能量化[1]", "恢复时间 SLA：原文无依据，不能量化[1]"]
