# 深度研究 Harness 调研与三模式覆盖审计

日期：2026-10-02。范围：官方文档、公开源码与本地实现核对；没有新增真实 Provider、Tavily 或裁判调用。本报告区分参考事实、项目事实和设计建议，不把他人性能宣传作为本项目成绩。

## 1. 结论与选择

建议增量改造已有 Harness：共享 Evidence 正文视图、支持引用与覆盖判断；保留 Plan-and-Execute 的顺序计划/replan、Multi-Agent 的监督委派/follow_up、Workflow 的固定外层流程。主质量结果用 Plan-and-Execute + Answer，其余模式完整对照；Report 分开验收。

这不是认定现有系统没有补查、引用或恢复，而是修复已有路径的信息不足和部署差异。详细设计见 [三模式设计](../superpowers/specs/2026-10-02-reliable-research-loop-design.md)。

## 2. 外部调研：采用什么，不采用什么

以下是调研中直接看到的机制；“本项目采用”列是根据项目现状作出的设计取舍，不是外部系统已经证明本项目效果更好。

| 官方参考 | 核对到的机制 | 本项目取舍 |
| --- | --- | --- |
| [LangGraph Workflows and agents](https://docs.langchain.com/oss/python/langgraph/workflows-agents) | 区分预定代码路径与动态 Agent；有并行、orchestrator-worker、evaluator-optimizer 等模式 | 保留不同策略的用途，不要求 Workflow 外层必须自适应，不增加第四个“万能调度器” |
| [Deep Agents overview](https://docs.langchain.com/oss/python/deepagents/overview) | 工具结果/上下文外置，文件读取支持 offset/limit，子 Agent 隔离上下文；规划是可选能力 | 参考按需读取，不迁移 SDK，不给研究员任意文件/执行权限；AGENTS.md 偏好记忆不替代已有事实 Store |
| [Open Deep Research 源码](https://github.com/langchain-ai/open_deep_research/blob/main/src/open_deep_research/deep_researcher.py) | research brief、监督委派、并发和迭代边界；研究结果压缩反馈给监督者 | 参考固定任务目标与反馈闭环；不直接复用压缩摘要作证据，不额外增加 think/compression 角色 |
| [GPT Researcher 深度研究源码](https://github.com/assafelovic/gpt-researcher/blob/main/gpt_researcher/skills/deep_research.py) | 跟踪 visited URLs、learnings/citations，用后续问题继续研究；有深度、并发与空结果终止 | 参考进展与无结果停止；不照搬递归研究树，不仅依据 URL 是否新出现判断正文补读的价值 |
| [Anthropic 多 Agent 研究系统](https://www.anthropic.com/engineering/multi-agent-research-system) | 委派边界、搜索启发式、出处定位与结果导向评估；质量 rubric 包括事实、引用、完整性、来源与效率 | 不让研究员重复完成同一任务；不要求检索唯一轨迹，不照搬其 Agent 数量或报告的收益数字 |
| [Anthropic Agent 评测方法](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents) | 区分任务、运行、轨迹、结果；结合代码、模型、人工评价，研究题评估 groundedness/coverage/source quality | 功能与质量分层；有出处的短回答不能掩盖遗漏，LLM 裁判需人工校准 |
| [LangGraph Persistence](https://docs.langchain.com/oss/python/langgraph/persistence)、[Checkpointers](https://docs.langchain.com/oss/python/langgraph/checkpointers) | Checkpoint 与 Store 分工；pending writes 可保留成功分支；从旧 checkpoint replay 后续节点会重新执行 | 恢复必须验证各模式的实际持久化组合；Checkpoint 不代替工具账本，也不等于网络调用 exactly-once |
| [Ragas FactualCorrectness](https://docs.ragas.io/en/latest/concepts/metrics/available_metrics/factual_correctness/)、[Faithfulness](https://docs.ragas.io/en/latest/concepts/metrics/available_metrics/faithfulness/)、[Agent/tool metrics](https://docs.ragas.io/en/latest/concepts/metrics/available_metrics/agents/) | F1 对 reference 的事实重合；Faithfulness 对检索材料的支持；目标与预期工具调用是不同指标 | 保留隔离 Ragas 0.4.3，三项原生质量指标固定身份；ToolCall 指标只用于有合法 reference_tool_calls 的任务 |

维护状态：Open Deep Research 页面显示已于 2026-08-21 归档，因此仅作源码参考。其余“main/latest”页面为本次阅读的可变参考，不是本项目锁定运行版本；实施若复制具体实现，应再记录确切提交/许可。生产与评测依赖不因本轮调研升级。

特别说明：今天 durable-execution 文档入口重定向至 persistence，恢复结论使用当前 Persistence / Checkpointers 页面；不把旧页面记忆当现行文档。

## 3. 本地实现证据

| 项目事实 | 代码入口 | 判断 |
| --- | --- | --- |
| Plan-and-Execute 已有 replan，默认最多 2 轮 | backend/src/deeptrace/strategies/plan_execute/graph.py、nodes.py | 不是缺机制；补查提示没有明确传入 reason/gaps/受支持发现 |
| Multi-Agent 已有 follow_up，默认最多 1 轮 | backend/src/deeptrace/strategies/multi_agent/graph.py、nodes.py | 同样是增强已有路径，不新建第二套重试 |
| Workflow 外层 evaluate → finalize | backend/src/deeptrace/strategies/workflow/graph.py:39 | 固定流程合理；内部研究循环仍可以调整搜索 |
| 三模式 evaluator 仅列 ID、标题、URL | 三模式 nodes.py 的 evidence_lines | 知道来源存在，却没有材料判定覆盖；这是共同缺口 |
| fetch preview 不含正文，研究工具没有 read_evidence | tools/adapters.py、harness/agent_tools.py、domain/tools.py | 正文已存入 EvidenceStore，但研究员未直接读到原文 |
| EVIDENCE_READ 枚举不等于研究员已授权读取 | tools/contracts.py、tools/policy.py | 当前研究员 capability allowlist 没有 EVIDENCE_READ；需显式改 schema、注册和授权 |
| Finding 只绑定 ID 和 confidence；引用检查只验证合法来源 | domain/evidence.py、responses/citations.py | 不证明引文蕴含或每条事实都有出处 |
| 未解决缺口列表累积 | plan_execute/state.py、multi_agent/state.py | 应分开最新 coverage 与历史诊断，避免已解决问题仍列 unresolved |
| 默认抓取只保留前 20000 字符 | tools/scraper/fetcher.py | 后续选段无法找回已丢掉的正文；正文保存与模型读取额度应分开 |
| 当前 canonical URL 对 source_quality 的启发式打分 | tools/adapters.py:_source_quality | 不能当作来源权威性或语义正确性的分数 |

### 恢复边界

- 图与 ResearchApplicationService 支持同 run/thread 的 checkpoint 续跑，共享 Agent 的工具重放有 Ledger 测试。
- tests/integration/test_recovery.py 的策略 registry 只注册 Workflow；不能把这组完整恢复断言直接宣传为另外两种模式已经分别验证。
- application/assembly.py 的本地配置使用 SQLite Checkpoint/Evidence/Memory，但 Ledger 是 InMemoryToolExecutionStore；数据库部署路径才使用 SqlAlchemyToolExecutionStore。
- runtime/local.py 重启会把 running/pending 标为 failed/interrupted；test_local.py 明确验证这一行为。持久化了历史，不等于用户入口已提供续跑。
- _SeededBudgets 成功时可以恢复工具消耗，但读取失败时目前警告后使用新计数；可靠恢复设计应 fail closed，不能悄悄恢复额度。
- 评测 real factory 使用 MeteredChatModel/RequestCounter 封顶真实 Provider 尝试；生产 assembly 直接构造 ChatModelGateway，并没有同等全运行计量封顶。分支轮数限制与输入 token 预算不能代替它。

这些边界来自读代码和已有测试，不是本轮新注入故障得到的三模式实测结果；相关行为尚未修改。

## 4. 备选路线与成本

1. 增量完善现有系统（推荐）：证据视图、覆盖/支持契约、定向补查和恢复验证，保持既有预算与存储所有权。没有新服务或运行框架，但需要维护自己的策略与评测。
2. 迁移 Deep Agents：可借用上下文/文件/子 Agent 的标准能力；需要重新适配权限、调用预算、Ledger、Checkpoint 与历史会话。对当前“evaluator 没读正文”的问题，迁移不是必要条件。
3. 接入完整 GPT Researcher：复用更大的研究引擎，但形成两套编排、模型、工具与费用治理；不适合当前简化目标。

Plan-and-Execute 内部也有取舍：每任务后 LLM 重规划更及时，但调用增加；先保留当前批次评估，传入真实缺口，再用重复来源、无进展与质量指标判断是否值得按任务评估。在线先用一层正文 evaluator + 确定性支持检查，不增加自审 Agent/多裁判投票/无界重写。

## 5. 测试执行记录

本轮只运行既有离线测试，没有新增测试代码；测试的 fixture/model/工具受控，不能称真实 API 质量成绩。以下是各命令的通过数，不可简单相加成独立总数：第一、第二组都含 2 个 smoke matrix 用例。

| 命令（在 backend 运行） | 结果 | 覆盖与限制 |
| --- | --- | --- |
| `.venv/Scripts/python.exe -m pytest tests/strategies tests/integration/test_mode_evaluation.py tests/integration/test_recovery.py tests/harness/test_agent_invariants.py tests/eval/test_smoke_matrix.py -q --tb=short` | 89 passed / 20.66s | 三模式策略、应用矩阵、共享 Agent 不变量；完整持久化恢复仍以 Workflow 为主 |
| `.venv/Scripts/python.exe -m pytest tests/eval tests/responses -q --tb=short` | 215 passed / 67.45s | 评测资产/身份/统计/计量、来源/选段/回答契约；不是新的 LLM 评分 |
| `.venv/Scripts/python.exe -m pytest tests/runtime/test_local.py tests/application/test_seeded_budgets.py -q --tb=short` | 12 passed / 4.35s | 本地重启中断与预算 seed 并发的当前行为；通过不意味着已具备本地自动续跑 |
| `.venv-ragas/Scripts/python.exe -m pytest evaluation/tests -q --tb=short` | 34 passed / 7.17s | 隔离 Ragas 适配/离线边界，不会因本轮测试产生新真实分数 |

测试缺口：三模式相同故障点的重建实例/子进程恢复、正文读取/引用 supports 的新行为、补查后需求关闭、真实 Plan-and-Execute + Answer 指标、三模式 live-web。设计中列为后续必须验收项，不能写成已经通过。

## 6. 真实数据与指标边界

现有一次真实模型校准是 1 道题 × Workflow/Baseline + Report，冻结本地真实官方资料，非实时网页。Workflow 的 AgentGoalAccuracy=1.00、FactualCorrectness F1=0.50、Faithfulness=0.48；Baseline generation_failed 的最终兜底文本三项均实测为 0。详细范围和原始哈希见 [旧校准报告](real-pilot-20261002.md)。这不是 Plan-and-Execute 分数，不能迁移成 Answer 基线。

本轮用户选择 Answer 主指标，Report 独立验收。前面询问中“便于与此前校准比较”的说法不准确，已更正：需要新建同模式/同输出条件的基线。

现有 research-v1 有 30 道 Agent 编写、来源核验的真实文档题，12 dev / 18 test，独立人工复核为 0。开发过程中读过/使用过的题不重新包装为未知题。来源家族隔离不能保证事实语义完全不重合；现有集用于工程校准，不自动代表广域深度研究能力。公开 DRB 任务导入也不等于已经有成绩。

成熟测评的最小可信交付是：原始资料与许可、任务/来源时间与哈希、配置/代码快照、三模式完整记录、主指标的实测分母与失败分解、固定 Baseline、独立评分预算、配对分析，以及可核验的人工抽查。人工复核必须真的发生，由审阅者给出记录，不能由 Agent 自己把字段改为 human_reviewed。

新增 paid research / search / judge 批次在执行前另行确认额度。本轮已完成的是调研、覆盖核对和待审阅设计；没有代码改造后的效果提升、统计显著性或商业 DeepResearch 优势结论。
