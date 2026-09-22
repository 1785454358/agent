# Agent Harness 实现差距与完善清单

这份文档负责把“完整的 Agent Harness 应该怎样设计”与当前 DeepResearch 工作树中的实际实现对齐。主文章负责讲清系统，本文负责回答面试中更尖锐的问题：哪些已经落到代码，哪些只完成了主链路，哪些仍需补齐。

## 阅读说明

- **已实现**：核心行为能在源码和确定性测试中验证。
- **部分实现**：主链路存在，但完整方案中的边界、故障场景或量化验证仍有缺口。
- **尚未实现**：目前只有设计方向，或者没有可重复验证的运行路径。

优先级分为“面试前必须”“重要”和“可选”。这里的“必须”不是要求把系统做成商业产品，而是要求简历中的核心表述能拿出代码、Trace 或测试证据。

## 能力总览

| 能力 | 当前状态 | 代码证据 | 主要缺口 | 推荐方案 | 验收方法 | 优先级 |
| --- | --- | --- | --- | --- | --- | --- |
| Shared Agent Loop | 已实现 | `harness/agent_executor.py`、`tests/harness/test_agent_executor.py` | 当前研究工具集合仍较小 | 保持循环与策略解耦，新增能力继续走统一执行器 | 展示一条 `prepare_context → model → tools → observe → policy` Trace | 面试前必须 |
| Context 不变量 | 已实现 | `harness/policies/agent_context.py`、`harness/model_gateway.py`、`tests/harness/test_agent_invariants.py` | Token 为保守估算，并非 Provider 精确计量 | 保留输出空间，按完整工具交换裁剪；后续接入 Provider usage | 构造超长历史，验证 instruction、original task、constraints 始终存在 | 面试前必须 |
| Completion nudge 与受控退出 | 已实现 | `harness/policies/execution.py`、`harness/agent_executor.py` | nudge 仍是通用提示，未按任务类型定制 | 维持有界次数，按失败原因生成更具体的补查提示 | 模拟模型提前结束，验证 nudge 上限和最终 Outcome | 面试前必须 |
| ModelGateway | 已实现 | `harness/model_gateway.py`、`tests/harness/test_model_gateway.py` | 尚无跨 Provider 的完整契约矩阵 | 为不同 Provider 增加相同输入输出与错误分类测试 | 注入超时、限流和非法上下文信封 | 面试前必须 |
| Tool 注册与白名单 | 已实现 | `tools/registry.py`、`tools/policy.py`、`tests/tools/test_registry.py`、`tests/tools/test_policy.py` | 当前业务能力主要是搜索与抓取，尚未形成大规模工具检索 | 工具数量增长后增加候选召回与排序层 | 注册允许/拒绝工具，验证调用者、模式和角色约束 | 面试前必须 |
| Tool 参数与 URL 安全 | 已实现 | `tools/gateway.py`、`tools/scraper/urls.py`、相关测试 | 内容级 Prompt Injection 防护尚不完整 | 在抓取后增加内容风险标注与隔离策略 | 覆盖私网地址、非法协议、未授权 URL 和重定向 | 面试前必须 |
| Tool 预算、缓存与 Singleflight | 已实现 | `tools/budget.py`、`tools/cache.py`、`tools/gateway.py`、相关测试 | 当前预算偏调用次数和网络单位，不等于真实账单 | 将 Provider usage 与工具成本写入统一可审计账本 | 并发相同请求，验证一次执行、预算预留与释放 | 重要 |
| 工具批有界并行与依赖等待 | 已实现 | `harness/agent_tools.py`、`tests/harness/test_agent_invariants.py` | 依赖表达仍以搜索授权 URL 为主，不是通用任务 DAG | 只在出现更多跨工具依赖后抽象显式依赖模型 | 同批发送独立搜索和依赖抓取，验证顺序及结果回写 | 面试前必须 |
| ToolMessage 完整配对 | 已实现 | `harness/agent_tools.py`、`tests/harness/test_agent_invariants.py` | 无关键缺口 | 保持所有异常路径都生成结构化失败消息 | 覆盖未知工具、非法参数、取消和终止性错误 | 面试前必须 |
| Evidence Store | 已实现 | `tools/evidence_store.py`、`persistence/evidence_store.py`、相关测试 | 证据版本更新和过期策略仍可加强 | 增加内容新鲜度、版本关系和失效原因 | 验证正文不进入 Graph State，State 只保存 Evidence ID | 面试前必须 |
| Citation 验证 | 部分实现 | `responses/citations.py`、`tests/responses/test_citations.py` | 能校验引用边界，但真实来源质量与蕴含关系仍需更系统评测 | 离线做 ID/URL/覆盖率检查，真实评测增加 faithfulness judge | 注入不存在的 Evidence ID、重复引用和无证据结论 | 面试前必须 |
| Checkpoint 恢复 | 已实现 | `harness/checkpoint.py`、`persistence/checkpoint.py`、`tests/harness/test_graph.py` | 需要更多进程中断和长任务恢复演示 | 固定故障点，记录恢复前后 State 与 Outcome | 工具节点后中断并恢复，验证不变量仍成立 | 面试前必须 |
| Execution Ledger 重放 | 部分实现 | `tools/execution_store.py`、`persistence/execution_ledger.py`、相关测试 | 分布式模式可持久化；本地模式 Ledger 仍是进程内实现，任意外部副作用也不能承诺 exactly-once | 为关键写工具设计远端状态核对接口，本地模式按需持久化 | 模拟提交成功后响应丢失，验证优先读取或核对既有结果 | 面试前必须 |
| 三类 Retry 所有权 | 已实现 | `harness/model_gateway.py`、`tools/gateway.py`、`harness/agent_executor.py`、恢复测试 | 需要一份集中式故障矩阵和演示 Trace | 将故障类型、所有者、上限和退出结果固化到评测集 | 分别注入 transport、semantic、recovery 故障 | 面试前必须 |
| AgentOutcome | 已实现 | `domain/agent.py`、`harness/policies/execution.py`、相关测试 | 上层产品展示可进一步强化 partial 与 unfinished todos | 保持 Outcome 为唯一受控退出契约 | 覆盖完成、部分成功、失败、取消和预算耗尽 | 面试前必须 |
| 长期记忆生命周期 | 已实现 | `harness/memory/`、`persistence/memory_store.py`、`persistence/chroma_memory.py`、相关测试 | 记忆质量、冲突消解和长期漂移缺少系统评测 | 建立带来源、置信度、有效期和冲突样例的记忆评测集 | 验证写入、召回、过期、替代和权威 Store 回查 | 重要 |
| 三种编排策略 | 已实现 | `strategies/workflow/`、`strategies/plan_execute/`、`strategies/multi_agent/`、对应测试 | Plan-and-Execute 是有界顺序计划，不应表述为通用依赖 DAG | 使用统一输入、预算和数据集做策略对照 | 固定问题与预算，比较完成、证据覆盖和调用成本 | 面试前必须 |
| 本地与分布式运行时 | 已实现 | `runtime/local.py`、`runtime/distributed.py`、`worker/service.py`、`queue/redis_streams.py`、集成测试 | 认证后的租户隔离和生产运维指标仍不足 | 在入口注入 tenant identity，并贯穿 Store、Evidence 与预算作用域 | 多 Worker、重复投递、租约竞争和取消传播测试 | 重要 |
| 离线 Agent Eval | 已实现 | `eval/`、`tests/eval/`、`tests/integration/test_mode_evaluation.py` | 数据集规模和难度仍小，当前更适合回归而非质量结论 | 扩充多跳、冲突来源、缺失证据和故障任务，并保留留出集 | 运行 scripted dataset，报告覆盖、引用、步骤、调用和终止原因 | 面试前必须 |
| 真实 Provider Eval | 部分实现 | `tests/real/test_eval_quality.py`、`eval/judge.py` | 依赖真实凭据，尚无稳定、可重复的基线报告 | 固定模型版本、温度、预算、重复次数和结果归档 | 独立运行 real marker，保存原始记录与聚合报告 | 重要 |
| 通用 Human-in-the-loop 审批 | 尚未实现 | 当前没有通用审批状态机和恢复协议 | 高风险写操作缺少统一暂停、审批、拒绝和过期语义 | 将 approval request 设计为可持久化事件，并由 Session Graph 恢复 | 构造批准、拒绝、超时和重复回调测试 | 可选 |
| 内容级 Prompt Injection 防护 | 尚未实现 | 已有 URL/SSRF 与工具边界，但没有完整内容风险管线 | 抓取正文可能包含诱导模型越权的指令 | 将外部内容标记为不可信证据，增加检测、引用隔离和红队评测 | 使用带恶意指令的网页语料，验证系统约束不被覆盖 | 重要 |
| 精确 Token 与真实成本计量 | 尚未实现 | 当前 `AgentOutcome.budget` 主要记录调用与步骤 | 无法从保守估算得出精确 Provider 账单 | 统一采集模型 usage、缓存命中和工具成本，按 run/mode/agent 聚合 | 对账 Provider usage，并验证恢复后不会重复累计 | 可选 |
| 认证后的多租户隔离 | 尚未实现 | `application/assembly.py` 明确保留 tenant identity 注入边界 | user/workspace 身份尚未贯穿所有存储和工具作用域 | 在 API 鉴权后注入租户身份，增加行级作用域和越权测试 | 两租户并发运行，验证 State、Evidence、Memory 与预算完全隔离 | 可选 |

## 面试前必须补齐

1. **保存两条可比较的完整 Trace。** 同一个问题分别使用 Plan-and-Execute 与 Multi-Agent，固定初始输入和预算，解释为什么产生不同调用路径。
2. **做一次恢复演示。** 在工具执行完成后的检查点制造中断，恢复后展示 ToolMessage、Evidence ID、Ledger 和 Outcome 没有丢失或重复。
3. **做一次 Context 对照。** 对比全量历史与按完整工具交换裁剪，记录约束保留、上下文大小和最终完成情况。
4. **固化离线评测报告。** 使用当前 `deeptrace.eval` 数据集输出三种策略的完成数、gold coverage、citation validity、调用次数、步骤数和终止原因。
5. **准备事实边界回答。** 明确哪些是离线模拟、哪些需要真实 Provider、哪些属于生产化方向。

## 重要但可分阶段完成

- 扩充离线数据集，加入多跳问题、来源冲突、搜索空结果、抓取超时和证据不足。
- 将记忆冲突、过期和替代纳入系统评测，而不只验证存取功能。
- 为关键外部写操作定义“查询远端真实状态”的恢复契约。
- 建立真实 Provider 的固定模型、预算和重复运行基线。
- 增加内容级 Prompt Injection 红队语料和可观测指标。

## 可选增强

- 通用 Human-in-the-loop 审批状态机。
- Provider 精确 Token 与真实费用对账。
- 认证后的多租户隔离与配额。
- 工具规模扩大后的候选召回与排序。
- 面向线上运行的 SLO、告警和容量测试。

## 本次验证记录

- 验证日期：2026-09-22
- 命令：`cd backend && uv run pytest -m "not real" -q`
- 结果：`482 passed, 2 deselected in 43.42s`
- 范围：当前工作树的确定性测试，包括 Harness、Tools、Persistence、Strategies、Runtime、Integration 与离线 Eval。
- 不包含：需要真实 API Key 或外部服务的 `real` 测试；因此本文不据此声明真实模型质量、线上吞吐或商业收益。

## 使用原则

主文章可以讲完整架构，简历只选择有证据的 3–5 个重点。面试时应主动给出边界：本地与分布式实现分别做到什么、离线与真实评测分别验证什么、Checkpoint 与 Ledger 能保证什么，以及为什么任意外部副作用不能轻率承诺 exactly-once。
