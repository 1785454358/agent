# 面向 Agent Harness 岗位的项目调研与优化分析

调研日期：2026-10-10。评估对象为当前工作区，包含尚未提交的修改。本文是调研与建议，不是已批准的实施规格；未修改业务代码、依赖或既有实验数据。

本文保留优化前的诊断。随后经用户授权实施，当前结果与验收见 [运行时优化记录](2026-10-10-harness-runtime-implementation.md)；下面列出的不足不能全部视为当前仍未解决的问题。

## 1. 判断与定位

建议保留 DeepResearch，逐步形成“可复用的 Agent 运行核心 + 研究业务实现”。研究 Agent 与 Coding Agent 共用模型/工具循环、上下文构建、预算、取消、状态恢复、执行记录和评测机制；研究的来源与引用治理，和 Coding 的文件/命令权限、工作区隔离、修改验证，则属于各自领域。

当前项目已经具备有价值的工程基础：ModelGateway、ToolGateway、并发预算准入、结构化退出、Checkpoint、Execution Ledger、带版本与坐标的证据交接、独立评测与实验身份。问题在于这些能力仍主要服务于研究业务，通用运行时边界和扩展成本不够直观。

应聘时最有价值的变化，是能够说明并证明：新增工具或第二种任务时，哪些代码无需修改；预算与恢复能保证什么；一次失败可以如何从轨迹定位。继续增加模式、角色或基础设施，不一定提高这方面的说服力。

这是根据用户的目标和源码作出的工程判断，不是对所有招聘岗位要求的统计结论。

## 2. 成熟实现的参考价值

| 参考 | 官方材料中可核对的机制 | 对本项目的启发 | 本轮取舍 |
| --- | --- | --- | --- |
| [Pi](https://github.com/earendil-works/pi) / [Agent Core](https://raw.githubusercontent.com/earendil-works/pi/main/packages/agent/README.md) | 模型访问、Agent Core、Coding 应用分层；区分应用消息与模型消息；上下文转换、工具前后钩子、执行事件 | 用小核心承载稳定循环，用明确扩展点接入领域行为；持久轨迹与模型输入视图分开 | 借鉴边界，不迁移 TypeScript，不复制整个 CLI |
| [Deep Agents](https://docs.langchain.com/oss/python/deepagents/overview) / [Middleware](https://docs.langchain.com/oss/python/langchain/middleware/overview) | 基于 LangGraph；上下文卸载、摘要、隔离子 Agent、可组合 middleware；当前文档中任务规划按需启用 | 能力可组合，业务不必写进核心；大结果外置与按需读取 | 优先参考组合方式；现有 EvidenceStore 已承担一部分外置职责，无需再造文件系统 |
| [LangGraph Persistence](https://docs.langchain.com/oss/python/langgraph/persistence) | Checkpointer 保存 thread 图状态；Store 保存跨 thread 数据，两者用途不同 | 明确状态、长期记忆和外部调用账本的所有权 | 继续使用 LangGraph，复查自己的恢复组合，不另造调度引擎 |
| [DeerFlow 2.0](https://github.com/bytedance/deer-flow) | 当前项目定位为包含 skills、子 Agent、记忆和 sandbox 的完整 harness；2.0 是对 1.x 的重写 | 研究可以成为通用 harness 的一个业务场景 | 作为能力地图和产品参考，不照搬完整平台的复杂度 |
| [Anthropic 长任务 Harness 实践](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents) | 跨上下文保存明确进展、增量执行、通过验证决定是否完成 | 恢复所需的工作状态与完成条件必须明确 | 借鉴验证与交接原则，不直接把 Coding 场景的进度文件设计塞进研究流程 |

以上是不同定位的框架、运行时和完整应用，并非同一层级的替代品，也没有进行性能排名。官网是本次在线查阅结果；本地 Pi 与 Deep Agents checkout 仅辅助理解源码，可能落后于在线版本。例如 Pi 本地材料仍有 `shouldStopAfterTurn`，在线材料已改为 `finishTurn`，建议只借鉴职责而不固定旧 API。

## 3. 当前项目值得保留的部分

- 模型与工具经过统一边界，工具参数校验、权限、URL 安全、预算、重试和执行记录已有实现。
- 三种策略通过 ResearchInput / ResearchOutcome 交接，共用执行器和证据评估，已经避免部分跨策略复制。
- 完整轨迹与有限模型视图分开；裁剪工具历史时关注消息配对，而非只裁字符。
- 证据使用 ID、版本、内容哈希、坐标与原文支持；不是只在答案后面附 URL。
- Checkpoint、Ledger、队列租约的分工已有代码与测试；架构文档承认外部调用窗口不承诺 exactly-once。
- 评测已有数据身份、原始失败记录、覆盖率、基线比较与隔离 scorer；不足是最新版本的验证覆盖与展示，而非完全缺少评测。

这些能力应作为重构时的保护对象。简洁应来自清楚的边界，不能通过移除运行约束获得。

## 4. 主要不足及源码依据

### 4.1 运行核心与研究领域耦合，是最重要的结构问题

`harness/agent_state.py` 的 AgentExecutorState 直接包含 ResearchTopicInput、Evidence anchor、research_findings 和 ResearchTopicOutcome。`harness/context.py` 同时放入通用网关、用户身份、记忆以及 research_max_pages、response_fact_review 等研究配置。`harness/agent_executor.py` 固定绑定 RESEARCH_TOOLS，finalize 直接生成研究结果。

这意味着已有共享运行时主要是在三种研究策略之间共享，尚不能据此宣称可直接复用于任意任务。

建议先建立逻辑边界：核心只负责消息、动作、工具执行、通用退出和资源消耗；研究插件负责取材、Finding、覆盖与引用。可以先沿用现有目录，通过一个小的 Agent 配置对象和结果适配器收敛接口，不必立刻搬动全部文件。

### 4.2 两种执行方式都有价值，但实际入口与文档不一致

`application/assembly.py` 当前默认装配 `build_batch_research_graph()`。分支主要按 `search → select_sources → fetch → read → synthesize → finalize` 推进，由程序执行取材。

`harness/agent_executor.py` 还保留 `context → model → tools → observe → policy` 的自主工具循环。最新主架构文档已经区分两者，但 `backend/README.md` 仍用共享自由循环解释一次生产请求，`docs/README.md` 也仍强调 Shared Agent Loop。

批量路径是合理的成本与时延选择，不能仅因为它更确定就判定其不符合 Harness 设计。应明确：外层是研究编排，默认分支执行器是批量路径；自由循环是另一种可用执行方式。面向岗位展示时，需要有自由循环的独立、可运行入口与案例。

不建议立即删除其中一条路径，也不建议把二者强行融合成带大量条件的万能循环。

### 4.3 工具注册是封闭集合，新增工具成本高

`domain/tools.py` 的 ToolName 固定为 search_web、fetch_page、read_evidence、search_memory。`tools/registry.py` 的 `_REQUIRED_CAPABILITIES` 也固定映射这些名称。`harness/agent_tools.py` 通过具体工具名处理完成、待办、Finding、搜索与抓取等行为，文件约 816 行。

当前设计对有限研究工具集是成立的，但新增一个本地文档工具，很可能需要同时修改领域枚举、注册校验、工具 schema、循环分派和权限映射。Registry 的存在本身尚不能证明开放扩展能力。

建议用注册的 ToolSpec 统一描述工具 ID、参数 schema、handler、权限要求及执行属性；核心按 spec 执行，领域处理通过显式适配器交接。工具名可扩展不等于权限自动放行：未知工具、能力缺失和未注册工具仍必须拒绝。并发、缓存与重放规则应能表达工具的副作用性质，不能将网页读取的规则原样套到文件修改。

只在确有第三方接入需求时再做 MCP 适配，当前无需插件市场或动态发现服务。

### 4.4 生产可观测性与评测计量没有贯通

`application/agent_adapter.py` 返回 AgentResult 时显式使用空的 TokenUsage、UsageBreakdown 和 stage_seconds。`harness/model_gateway.py` 返回模型响应，但没有统一生成模型调用的开始、完成、失败和 usage 事件。`observability/events.py` 的汇总主要面向工具。

`eval/telemetry.py` 已经有 Provider attempt 和缺失 usage 的计量。因此不是没有监控代码，而是生产与评测没有复用同一份运行指标契约。

优先在模型网关补齐调用记录：run / branch / role / call、起止与耗时、尝试次数、实际 input/output usage、估算标志及错误原因。再贯通到 AgentResult 和前端。没有服务商 usage 应显示 unknown/estimated，而不是零。事件与日志保留相关 ID 即可先满足定位需求，OpenTelemetry / Langfuse 适配可以后置。

SSE 已有进度展示，但当前模型网关使用 ainvoke；尚未看到统一的模型增量输出接口。完整 token 流式输出对交互型 Coding Agent 更重要，可在指标契约稳定后补充。

### 4.5 恢复状态与资源预算的保证范围不一致

`harness/model_budget.py` 明确声明模型次数、输入额度和时间计数仅在单进程内维护。`assembly.py` 用 run_model_gateways 字典复用同一进程的 run 预算，但重新启动后会重新创建计数和起始时间。

本地模式的 Checkpoint / Evidence / Memory 使用 SQLite，工具 Ledger 仍是 InMemoryToolExecutionStore；分布式 Ledger 才是 SQL 存储。`_SeededBudgets` 可以从 SQL Ledger 重建工具消耗，但失败时记录日志并继续使用新计数。

因此，“图状态可恢复”不能概括成“运行全部约束都能跨进程恢复”。这些是代码中的已知边界，本轮没有进行新的崩溃注入实验。

建议先统一 run 的使用量快照和期限语义：已消耗模型额度不得因接管而恢复；暂停时间是否计入期限要写清楚；预算恢复失败应形成受控失败或保守额度。工具 Ledger 与模型 usage 可以共用 run 身份，但不必合成一个笼统的大型账本。

另外，run_model_gateways 未见结束后的释放路径，应在 run 生命周期结束后释放或有限保留；这是长期进程的维护风险，尚未测量实际内存影响。

### 4.6 模型协议依赖提示文本，供应商适配混在组合根

`model_gateway.py` 通过扫描消息中的中文字符串“原始任务：”“当前约束：”验证上下文。它保护了当前研究提示，但格式、语言改变时容易让协议校验与文本呈现互相牵制。

`assembly.py` 同时包含特定豆包模型名称判断、thinking 参数、JSON 角色配置，以及存储组装、SQLite schema 创建与迁移，约 589 行。

建议用结构化 ModelRequest 表达 instruction、任务、约束和实际 messages，在上下文构建处验证必要字段；Gateway 只验证协议与执行模型 I/O。供应商兼容选项独立为一个小配置/适配函数；数据库初始化移到 persistence。无需多级 ModelFactory 或通用依赖注入容器。

### 4.7 模块很多，但职责仍有集中点

当前 backend/src/deeptrace 约 163 个 Python 文件、2.5 万行，包含评测代码，不能简单将总行数解释为过度设计。值得关注的是职责集中：evidence_evaluation.py 约 849 行，responses/graph.py 约 771 行。

前者包含来源材料、支持解析、覆盖规范化、补查规划和退出决策；后者包含内容解析、提示组装、生成纠偏、质量复查与引用验证。按这些职责拆分能降低理解成本；按任意行数上限拆文件只会增加跳转。

三种策略已经共享 common 和 evidence_evaluation，不应宣称它们完全复制。后续若继续抽公共逻辑，应让策略保留各自调度行为，避免制造一个充满 mode 判断的基础策略类。

### 4.8 工程验证丰富，但最新版本的质量证据仍需扩大

项目已有不少真实诊断、冻结资料评测、公开任务子集及严谨的失败记录。最新公开展示主要是 asyncio 已知题和量子研究题的少量运行，不能代表当前工作区在多领域上的稳定表现。历史自由循环的评测成绩，也不能直接作为当前批量路径及新增 fact review 的成绩。

建议做小而稳定的验证集：单来源、多跳、版本限制、冲突证据、搜索失败、长上下文等不同任务；冻结模型、代码、配置与数据身份。比较批量路径和自主循环、是否补查、是否记忆时，一次只变化一个因素。报告成功/部分/失败、来源与事实质量、调用数、总 token、耗时及评分覆盖；质量与速度同时观察。

先用 10–20 个有明确验收条件的任务作为工程基线，预算允许时每题重复 2–3 次；这只是规模建议，不是统计充分性的承诺。人工复核一部分逐条结论，校准模型裁判。故障恢复和预算验证可以离线独立进行。

## 5. 推荐的最小模块边界

这是职责图，不要求立即新建六层目录：

```text
API / CLI / Worker
        |
Application：run 生命周期、装配、结果交接
        |
Research：规划、批量取材、证据覆盖、回答引用
        |
Agent Core：上下文 → 模型 → 工具 → 观察 → 退出
        |
Ports：Model / Tools / Checkpoint / Events
        |
Adapters：模型供应商、网页、SQL、队列
```

研究的批量执行器可以直接使用 Ports，不必人为多走一次自主模型循环。依赖关系的目标是：Research 可以使用 Core，Core 不导入 Research 的 Finding、来源策略和输出契约。

核心优先只稳定三类公开契约：Agent 配置、Run 输入/结果、ToolSpec。扩展点先放在实际有需求的位置：模型输入构建、工具执行前后、完成判断。监控优先复用既有 Gateway/EventSink；安全和预算是必经边界，不允许随意绕过的可选钩子。

长期记忆先保留现有实现，但在入口上作为可选能力清楚表达；跨会话事实记忆不应成为一个普通工具循环启动的前提。

## 6. 三条路线与取舍

| 路线 | 收益 | 成本与风险 | 适配目标 |
| --- | --- | --- | --- |
| A. 增量抽出小核心，保留研究业务（推荐） | 延续已有治理与证据优势，能展示复用边界 | 需要保护历史状态与研究契约，逐步验证 | 通用 / Coding Agent 运行时岗位 |
| B. 收敛为简洁研究流水线 | 默认路径最容易理解与维护 | 自主循环和通用运行时展示较弱；删模式前需证明它们价值不足 | 研究 Agent 应用岗位 |
| C. 迁移 Deep Agents 等 SDK | 复用标准扩展与环境能力 | 权限、预算、证据、Ledger、历史状态均要适配，可能同时维护两套机制 | 现有运行核心确实成为瓶颈时 |

当前没有证据表明必须更换框架，因此优先 A。三种策略先保留为对照，选 Plan-and-Execute 作为主入口；用验证决定是否收敛，而不是为减少目录直接删除。

## 7. 优化顺序与验收方向

| 优先级 | 内容 | 可观察的验收结果 |
| --- | --- | --- |
| P0 | 对齐真实默认路径、配置、README 与架构；冻结当前基线 | 读者能从入口走通实际执行链；知道自由循环与批量路径的用途 |
| P0 | 贯通生产模型 usage、角色耗时与失败事件 | 每个 run 能定位调用、资源消耗及退出原因；缺失值不伪装成 0 |
| P0 | 明确并补齐预算与恢复边界，处理 run 资源释放 | 同 run 接管后额度不会恢复；无法恢复账目时有受控结果 |
| P1 | 将领域 Finding/完成判断从循环中移出，工具通过 spec 执行 | 一个非研究工具加入时不改核心分派；权限规则仍明确 |
| P1 | 收敛 Context 与模型请求契约，拆开装配中的迁移/供应商细节 | 普通任务不需要填入研究配置；更换提示语言不破坏运行协议 |
| P1 | 稳定小型评测与故障矩阵，验证重构未损伤研究 | 结果与基线可对照，失败和缺失评分可见 |
| P2 | 增加第二种任务的薄示例 | 用同一核心读取本地资料并生成可核对结果，不复制运行治理 |
| P2 | 若目标岗位强调 Coding，再加受限文件修改/测试场景 | 明确目录权限、diff、命令取消与验证结果；不需要完整 IDE |

第二种任务先选本地文档或小型代码库的只读分析，是低成本的通用性证明。但只读示例不能证明 Coding 的写入安全；若展示文件修改，需要真实工作区约束和副作用验证。

暂不优先：Agent 市场、通用 DAG 平台、多级插件系统、自动能力发现、更多监督角色、多裁判投票、另造分布式调度或全面迁移 SDK。现有 Redis/MySQL/Chroma 可以作为高级运行配置，面试主路径保持易启动。

## 8. 本轮验证与限制

阅读了当前源码、主要架构与展示文档、近期提交及部分评测记录；在线核对官方框架材料，并参考本地 Pi/Deep Agents 源码。没有真实模型、搜索或裁判调用，也未测量性能收益。

在 backend 执行既有测试：

```powershell
uv run --no-sync pytest tests/application/test_batch_assembly.py tests/harness/test_model_run_budget.py tests/harness/test_agent_invariants.py tests/tools/test_gateway.py tests/persistence/test_execution_ledger.py -q
```

结果：62 passed，10.16 秒。覆盖所选装配、模型预算、消息/退出不变量、工具 Gateway 和执行 Ledger；不是全量回归，也不证明跨进程模型预算恢复、真实模型质量或 Coding 写入安全。

面试定位建议：围绕 DeepResearch 实现了受预算、权限与恢复约束的共享 Agent 运行时，并通过证据交接验证研究场景。完成抽离及第二场景验证后，再强调可复用 Harness。不要提前将后续计划写成已经实现的通用 Coding 平台。
