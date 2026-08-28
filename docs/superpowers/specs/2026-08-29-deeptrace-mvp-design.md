# DeepTrace MVP 设计规范

- 状态：已确认，待最终复核
- 日期：2026-08-29
- 目标周期：1～2 个月
- 目标岗位：Agent / 大模型应用开发
- 架构图：[DeepTrace MVP 架构](../../design/deeptrace-mvp-architecture.html)
- 数据模型图：[数据模型与运行数据流](../../design/deeptrace-data-model-and-flow.html)

## 1. 项目定位

DeepTrace 是一个面向实时网络信息的、可评测的多智能体深度调研系统。系统通过需求解析、研究规划、并行检索、证据抽取、事实验证、缺口分析和报告写作形成受控研究闭环，生成带可追溯引用的报告。

一句话定义：

> 一个能够自主拆解问题、多轮搜索网页、验证关键事实，并生成带可追溯引用报告的多智能体 DeepResearch 系统。

项目重点不是复刻通用聊天界面，而是展示以下 Agent 工程能力：

- 受控 Multi-Agent 编排。
- 计划、执行、反思和自适应停止。
- 搜索、网页抓取和结构化工具调用。
- Claim、Evidence 和 Source 构成的证据链。
- 面向研究结果的短期与长期 Memory。
- Agent 评测、消融实验和运行可观测性。
- 失败隔离、预算控制、恢复、降级和安全边界。

## 2. 目标与非目标

### 2.1 目标

MVP 必须支持：

1. 接受中文或英文自然语言研究问题。
2. 在必要时最多追问一次，形成结构化 ResearchBrief。
3. 将问题动态拆成 3～6 个可独立验收的研究子任务。
4. 最多使用 3 个 Researcher 并行搜索和读取网页。
5. 从网页正文中保存可定位的 Evidence，而不是把搜索摘要当作证据。
6. 把长段结论拆成最小可验证 Claim，并建立 Claim 与 Evidence 的支持、反驳或背景关系。
7. 根据证据缺口执行最多一轮补充研究。
8. 仅使用已验证证据生成带行内引用的报告。
9. 保存研究状态、证据、报告和运行事件，支持取消、恢复和更新研究。
10. 使用中文评测集量化报告质量、可靠性、成本和延迟。

### 2.2 非目标

MVP 不包含：

- 强化学习、模型微调或训练基础模型。
- 自研搜索引擎。
- 需要登录态的网站自动化。
- 图片、视频和音频研究。
- PDF 全文研究不是验收要求；MVP 只保证 `text/html`，PDF 文本抽取作为可选增强。
- 超过三层的 Agent 层级或 Agent 自由群聊。
- 多租户、付费和复杂权限管理。
- 原生移动端。
- Word、PDF 等复杂报告导出。
- 完整知识图谱可视化。
- 定时新闻推送。

后续可扩展定时研究、报告变化检测、公开 Agent SDK 和更多数据源，但它们不影响 MVP 验收。

## 3. 主要用户场景

### 3.1 AI 热点调研

用户提出“调研今天 AI Agent 领域值得关注的新闻”。系统识别时间范围与重要性标准，将任务拆为模型、产品、开源、论文和行业事件等子主题，并行搜索官方博客、GitHub、论文和专业媒体。系统对事件去重、校验发布时间、交叉验证关键事实，最后按重要性输出带引用报告。

### 3.2 大厂招聘调研

用户提出“调研 2027 届字节跳动 Agent 开发相关岗位，总结共同要求、岗位差异和适合准备的项目”。系统优先读取招聘官网，提取岗位职责、必需能力和加分项，区分官方要求与二次解读。再次运行时，系统召回历史证据并重新验证时间敏感页面，输出新增、变化和失效结论。

### 3.3 开源项目对比

用户要求比较两个 DeepResearch 项目。系统优先读取官方仓库、文档、许可证和发布信息，将功能、架构、维护状态和评测结果分别建模为 Claim，避免把不同版本的信息混在一起。

## 4. 开源复用原则

DeepTrace 使用独立仓库、独立核心数据模型和独立研究执行链。通用基础设施直接复用，现有 DeepResearch 项目用于学习和评测基线。

### 4.1 可直接复用

- LangGraph 的状态图、Checkpoint 和中断恢复能力。
- FastAPI 与 SSE/WebSocket 基础能力。
- PostgreSQL、pgvector 和缓存组件。
- 搜索 API、Playwright 和正文解析库。
- 模型官方 SDK 或统一 Model Gateway。
- OpenTelemetry、LangSmith 等追踪基础设施。
- 合规使用的公开评测数据和格式。

### 4.2 只参考设计

- Open Deep Research 的 Supervisor–Researcher、上下文压缩和评测接入方式。
- GPT Researcher 的 Planner–Execution–Publisher、Retriever Provider 和产品化设计。
- 两个项目的测试用例、故障记录和架构取舍。

### 4.3 必须独立实现

- ResearchRun 和 ResearchTask 状态模型。
- Planner 的任务规划协议与完成标准。
- Researcher 的工具使用边界。
- Evidence Graph 与 Claim 验证协议。
- Gap Controller 的补搜与终止策略。
- 研究 Memory 的失效和重新验证逻辑。
- Agent 评测、消融实验和成本核算。

如确需复制少量开源代码，必须遵守原许可证、保留声明并在仓库中标出来源。核心 Agent 图、Prompt 和终止策略不直接复制。

## 5. 总体架构

系统分为四层。

### 5.1 交互与 API 层

- Web UI：提交问题、确认 ResearchBrief、查看进度、证据和报告。
- FastAPI：提供任务、取消、恢复、更新研究、历史记录和报告接口。
- SSE：向前端推送阶段、搜索、抓取、验证、错误、Token 和耗时事件。
- Run Service：创建、恢复、取消 ResearchRun，并统一管理预算。

### 5.2 Agent 编排层

- Intake：解析用户意图，必要时追问一次。
- Planner：生成 3～6 个子任务及各自完成标准。
- Researcher：最多三个并行实例，负责搜索、抓取和证据抽取。
- Verifier：检查 Claim 是否被 Evidence 支持，处理冲突和时效性。
- Gap Controller：根据覆盖缺口和剩余预算决定补搜或停止。
- Report Writer：只使用允许发布的 Claim 和 Evidence 生成报告。

这些名称表示职责清晰的执行单元，不是可以自由聊天的角色。所有单元使用结构化输入输出，并通过持久化状态协作。

### 5.3 工具与证据层

- Search Gateway：封装搜索 Provider、域名策略、结果去重和限流。
- Web Fetcher：负责普通 HTTP 抓取、浏览器降级、超时和响应限制。
- Content Extractor：提取正文、标题、作者、发布时间和原文定位信息。
- Evidence Store：保存 Claim、Evidence 与 Source 的可追溯关系。

### 5.4 状态与基础设施层

- PostgreSQL 保存任务、来源、证据、结论、报告和运行事件。
- pgvector 支持历史 Evidence 和 Claim 的语义召回。
- LangGraph Checkpoint 保存执行状态并支持恢复。
- Tracing/Metrics 保存模型、工具、Token、费用、耗时和错误指标。

## 6. 核心数据模型

### 6.1 ResearchRun

表示一次完整研究，包含原始问题、ResearchBrief、状态、轮次、预算、当前阶段、父运行 ID、Checkpoint 和统计指标。父运行 ID 用于“更新研究”。

状态至少包括：`created`、`clarifying`、`planning`、`researching`、`verifying`、`writing`、`completed`、`partially_completed`、`failed` 和 `cancelled`。

### 6.2 ResearchTask

表示 Planner 创建的研究子任务，包含研究问题、完成标准、优先级、状态、查询历史、覆盖分数和失败原因。

### 6.3 Source

表示原始网页来源，包含规范化 URL、内容哈希、标题、作者、发布时间、抓取时间、来源类型、域名质量、正文快照和抓取状态。

URL 与内容哈希共同用于识别地址重复、镜像页面和内容更新。

### 6.4 Evidence

表示可以定位到来源正文的最小证据片段，包含原文、定位信息、抽取摘要、所属子任务、时效范围、提取置信度和向量表示。

### 6.5 Claim

表示最小可验证事实陈述，包含文本、重要性、时间敏感性、状态和综合置信度。

状态至少包括：`candidate`、`verified`、`disputed` 和 `insufficient`。

`verified` 可以作为确定事实进入正文；`disputed` 只能进入“冲突与不确定性”部分，并必须同时展示相互冲突的证据；`insufficient` 不能作为事实发布，只能被列为研究缺口。

### 6.6 ClaimEvidence

表示 Claim 与 Evidence 的多对多关系，关系类型为 `supports`、`refutes` 或 `context`，同时保存语义支持分、Verifier 理由和是否允许进入报告。

### 6.7 Report

保存 Markdown 正文、结构化摘要、引用映射、报告版本、覆盖率、引用指标、成本和耗时，并关联实际使用的 Claim 集合。

### 6.8 RunEvent

保存 Agent、Tool、阶段、事件类型、开始和结束时间、Token、费用、错误码、重试次数以及面向 UI 的安全摘要。

## 7. 完整研究流程

1. Run Service 创建 ResearchRun，Intake 生成 ResearchBrief、预算和来源偏好。
2. Planner 创建 3～6 个 ResearchTask，并为每项写明完成标准。
3. Researcher 并行生成搜索查询、选择候选来源并读取正文。
4. 系统规范化 URL、计算内容哈希，落库 Source 和 Evidence。
5. Researcher 从 Evidence 提取原子 Claim，不直接生成最终报告。
6. Verifier 建立 ClaimEvidence，判断支持、反驳或背景关系。
7. Gap Controller 计算任务覆盖缺口。有缺口且有预算时创建补充任务，最多进入第二轮。
8. Report Writer 读取可发布 Claim 与 Evidence，生成报告和行内引用。
9. 系统保存指标、运行轨迹、报告和可用于后续召回的研究记忆。

核心不变量：

> Report Writer 不能读取原始搜索结果，也不能凭对话上下文补充外部事实。进入报告的外部事实必须存在 `Claim → ClaimEvidence → Evidence → Source` 路径。

## 8. Memory 设计

MVP 不创建语义含糊的通用 Memory 表。历史 ResearchRun、Claim 和 Evidence 本身构成研究记忆。

新研究开始时：

1. 使用问题和子任务向量召回相关历史 Claim/Evidence。
2. 根据发布时间、抓取时间、内容哈希和时间敏感性判断证据状态。
3. 将证据分类为可复用、需要重新验证或已经失效。
4. 只把可复用或重新验证成功的证据交给 Verifier。

“更新研究”创建新的 ResearchRun，并通过父运行 ID 关联旧报告。新报告需要明确展示新增、变化、失效和保持不变的结论。

## 9. 预算与终止策略

每个 ResearchRun 持有持久化 BudgetLedger。默认限制如下：

- 最多两轮研究。
- 最多三个并行 Researcher。
- 最多读取 15 个不同网页。
- 每个子任务最多生成三个搜索查询。
- 单网页响应大小和正文长度受限。
- 默认运行时限约八分钟。
- Token、费用和工具调用次数均可配置。

每次模型或工具调用前预留预算，调用结束后结算实际消耗。预算不足时不开始新调用。

满足以下条件可以提前停止：

- 所有高优先级子任务达到覆盖目标。
- 重要 Claim 有一个在其权威范围内的 A 级来源，或两个独立可靠来源。
- 没有影响主要结论的未解决冲突。
- 新一轮搜索没有带来足够的新证据。

达到硬预算后停止补搜，但仍验证现有证据并生成标明缺口的部分报告。

## 10. 来源质量策略

- A 级：招聘官网、公司公告、论文原文、官方文档、政府数据和项目官方仓库。
- B 级：具有编辑审核的专业媒体、研究机构和可信行业报告。
- C 级：论坛、个人博客、聚合页和社交媒体。

一个 A 级来源只能证明其权威范围内的官方事实。没有合适 A 级来源时，重要 Claim 优先要求两个独立 A/B 级来源。C 级来源可以发现线索、观点和用户反馈，不能单独证明关键事实。

Verifier 不能仅依据来源等级通过 Claim，还必须判断 Evidence 原文是否真正支持该陈述。

## 11. 异常处理与降级

### 11.1 局部异常

- 搜索超时或限流：指数退避重试一次，再切换备用 Provider。
- 网页 403 或超时：普通 HTTP 抓取失败后尝试浏览器抓取，仍失败则放弃。
- 只有搜索摘要：可用于发现页面，不能保存为 Evidence。
- 正文解析失败：尝试备用解析器，仍失败则记录 `extract_failed`。
- LLM 格式错误：按 Schema 修复或重试一次。
- Researcher 失败：子任务重新入队一次，不影响其他子任务。
- Verifier 无法判断：Claim 标记为 `insufficient`，不作为确定事实发布。
- 来源冲突：Claim 标记为 `disputed`，报告并列呈现不同证据。
- 服务重启：从 Checkpoint 恢复，不重复已完成调用。
- 用户取消：停止派发新任务，保存已有证据，Run 标记为 `cancelled`。

### 11.2 整体失败

只有 Planner 无法生成合法任务、全部搜索 Provider 不可用、数据库/Checkpoint 无法写入或完全没有获得有效网页时，ResearchRun 才标记为 `failed`。

### 11.3 降级顺序

1. 降低并发数。
2. 停止低优先级子任务。
3. 停止第二轮补充研究。
4. 使用已有证据生成部分报告。
5. 在报告开头列出未覆盖问题和失败来源。

系统不能静默降级，也不能在证据不足时生成看似完整的结论。

## 12. 安全边界

网页内容全部视为不可信数据：

- 网页文本不能改变系统指令、工具权限或研究目标。
- Tool 输出和系统指令使用分离的数据结构。
- 禁止访问本机、私有网段和 `file://` 等地址，防止 SSRF。
- 不执行网页代码、命令或下载文件。
- 限制重定向次数、响应大小和抓取时间。
- 网页文本、引用和运行事件写入前端前必须转义。
- API Key、内部 Prompt 和完整模型上下文不能进入 RunEvent。
- 前端只显示运行决策的安全摘要，不展示模型私有思维链。

## 13. 测试策略

### 13.1 单元测试

覆盖 URL 规范化、内容哈希、来源分级、BudgetLedger、状态转换、Evidence/Claim 约束、停止条件、引用渲染和证据失效规则。测试完全确定，不连接网络或真实模型。

### 13.2 工作流测试

使用 Fake LLM 和 Fake Tools 覆盖：

- 正常两轮研究和第一轮提前停止。
- 一个 Researcher 失败。
- 搜索限流与 Provider 切换。
- 网页全部不可读。
- Verifier 发现冲突。
- 预算耗尽后生成部分报告。
- Checkpoint 恢复和用户取消。
- 网页 Prompt Injection。

### 13.3 集成测试

分别验证 Search Provider Adapter、HTTP/浏览器抓取降级、正文与元数据提取、PostgreSQL/pgvector/Checkpoint、Structured Output Schema、SSE 和任务取消。

### 13.4 端到端测试

准备五个成本受控的真实网络问题。测试不比较完整文本，只验证任务完成、引用可访问、关键事实有证据链、没有孤立引用且成本和耗时不超限。

## 14. Agent 评测

### 14.1 中文评测集

建立 30 个问题：

- AI 热点与时效信息：5 个。
- 招聘与公司调研：5 个。
- 开源项目对比：5 个。
- 技术方案调研：5 个。
- 多来源冲突：5 个。
- 异常与安全：5 个。

20 个问题作为开发集，10 个作为隐藏测试集。动态问题保存评测时间和当时网页快照，以便复现。

### 14.2 质量指标

- Citation Validity：引用是否可访问且指向正确页面。
- Citation Correctness：Evidence 是否支持相邻 Claim。
- Citation Completeness：重要事实是否都有引用。
- Research Coverage：是否回答全部核心子问题。
- Source Quality：一级来源和独立来源比例。
- Conflict Handling：是否识别并呈现冲突证据。
- Freshness：时间敏感信息是否在有效时间范围内。

### 14.3 工程指标

- 任务成功率、平均耗时、Token 和模型费用。
- 搜索、抓取和模型调用次数。
- 重复网页比例和每个有效 Evidence 的平均成本。
- Checkpoint 恢复成功率。

评测结合确定性代码检查、LLM Judge/NLI 和隐藏测试集人工抽查，不把单一 LLM Judge 结果当作唯一结论。

### 14.4 Baseline 与消融实验

至少比较：

1. 单次搜索加直接回答。
2. 单 Researcher、无补充循环。
3. DeepTrace 去掉 Verifier。
4. DeepTrace 固定执行两轮。
5. DeepTrace 完整版。
6. 在小规模测试集上运行 GPT Researcher 和 Open Deep Research 作为外部参考。

Memory 使用首次研究与更新研究任务单独评测，比较重新访问网页数量、证据复用率、变化识别准确率、成本、耗时和过期证据误用率。

所有结果同时报告质量和成本，不能只展示综合分数。

## 15. MVP 验收标准

- 30 个评测问题和评测脚本可以重复运行。
- 引用可访问率目标不低于 90%。
- 引用支持率目标不低于 80%。
- 核心问题覆盖率目标不低于 80%。
- 无来源事实比例目标不高于 10%。
- 任务成功完成率目标不低于 90%。
- Prompt Injection 测试不能改变 Agent 指令或触发危险工具。
- 至少完成三组消融实验。
- Docker Compose 可以启动 API、数据库和 Web UI。
- README 包含架构、快速启动、演示问题和真实评测结果。
- 仓库提供架构图、评测报告和 3～5 分钟演示视频。

以上百分比是验收目标，不是预先承诺的实验结果。未达到目标时也必须保留真实数据并分析原因。

## 16. 设计决策摘要

1. 采用受控工作流式 Multi-Agent，不采用自由对话式 Agent 群聊。
2. Evidence Store 是外部事实进入报告的唯一通道。
3. 历史 Claim 和 Evidence 直接构成研究 Memory，不增加抽象 Memory 表。
4. 搜索摘要只能发现来源，不能作为正式证据。
5. 默认最多两轮研究、三个 Researcher 和 15 个网页。
6. 质量不足或预算耗尽时返回明确的部分报告，不静默降级。
7. 用 Baseline 和消融实验证明每个 Agent 机制的实际价值。

## 17. 参考项目

- [LangChain Open Deep Research](https://github.com/langchain-ai/open_deep_research)
- [GPT Researcher](https://github.com/assafelovic/gpt-researcher)
- [Deep Research Bench](https://github.com/Ayanami0730/deep_research_bench)

参考项目只用于学习、合规复用通用思想和建立评测基线。DeepTrace 的核心实现必须能够独立说明、独立测试和独立演进。
