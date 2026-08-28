# DeepTrace MVP 实施计划

- 状态：待用户复核
- 日期：2026-08-29
- 依据：[DeepTrace MVP 设计规范](../specs/2026-08-29-deeptrace-mvp-design.md)
- 预计周期：6 周，可压缩为 4 周核心版
- 执行原则：测试优先、纵向切片、每项独立提交、真实指标不美化

## 1. 实施目标

在不复制 Open Deep Research 或 GPT Researcher 核心执行链的前提下，实现一个可部署、可演示、可评测的 DeepResearch Agent：

- 用户提交研究问题后，系统能够规划、并行研究、验证证据、补充搜索并生成带引用报告。
- 任一外部事实必须具有 `Claim → ClaimEvidence → Evidence → Source` 路径。
- 系统支持预算控制、任务取消、Checkpoint 恢复、部分失败和研究更新。
- 仓库包含自动化测试、30 题中文评测集、消融实验、架构文档和演示材料。

## 2. 建议技术栈

### 2.1 后端

- Python 3.11+
- uv 管理依赖和虚拟环境
- FastAPI + Pydantic
- LangGraph 负责状态图与 Checkpoint
- SQLAlchemy + Alembic + PostgreSQL
- pgvector 负责历史 Claim/Evidence 召回
- httpx 负责普通网页获取
- Playwright 作为 JavaScript 网页降级方案
- Trafilatura 或等价库负责正文抽取
- OpenTelemetry 记录模型、工具和阶段指标

### 2.2 模型与搜索

- `ModelGateway` 面向支持 Structured Output 和 Tool Calling 的模型。
- 第一版实现一个 OpenAI-compatible Provider，具体模型由环境变量配置。
- `SearchProvider` 第一版实现一个主 Provider 和一个备用 Provider。
- 所有 Provider 必须有确定性的 Fake 实现，测试不依赖真实网络和模型。

### 2.3 前端与基础设施

- React + TypeScript + Vite
- SSE 接收研究进度事件
- Docker Compose 启动 PostgreSQL、API 和 Web UI
- pytest、pytest-asyncio、respx、ruff 和静态类型检查
- 前端使用 Vitest 和 Testing Library

不在第一版引入 Redis、Celery、Kubernetes 或微服务拆分。研究任务在独立 Run Worker 中执行，PostgreSQL 和 LangGraph Checkpoint 提供持久化与恢复能力。

## 3. 目标目录结构

```text
agent_new/
├── backend/
│   ├── pyproject.toml
│   ├── alembic.ini
│   ├── migrations/
│   ├── src/deeptrace/
│   │   ├── api/
│   │   ├── agent/
│   │   │   ├── nodes/
│   │   │   ├── graph.py
│   │   │   └── state.py
│   │   ├── domain/
│   │   ├── db/
│   │   ├── providers/
│   │   │   ├── llm/
│   │   │   ├── search/
│   │   │   └── fetch/
│   │   ├── services/
│   │   ├── evaluation/
│   │   ├── config.py
│   │   └── main.py
│   └── tests/
│       ├── unit/
│       ├── workflow/
│       ├── integration/
│       ├── e2e/
│       └── fixtures/
├── frontend/
│   ├── src/
│   └── tests/
├── evals/
│   ├── datasets/
│   ├── fixtures/
│   ├── baselines/
│   └── results/
├── docs/
├── docker-compose.yml
└── README.md
```

目录可以在实施时小幅调整，但领域模型、Provider、Agent Node、服务和评测代码必须保持边界清晰。

## 4. 全局开发循环

每个任务按同一顺序执行：

1. 添加失败测试或可复现 fixture。
2. 运行目标测试，确认失败原因符合预期。
3. 实现通过测试所需的最小代码。
4. 运行目标测试、相关模块测试和静态检查。
5. 删除重复逻辑，保持文件职责单一。
6. 更新必要文档并独立提交。

每个阶段结束时执行完整质量门禁：

```text
backend: unit + workflow + integration tests, lint, type check
frontend: unit tests, lint, production build
repository: Docker Compose smoke test
```

真实模型和真实网络测试单独标记，默认测试套件不能因外部 API 缺失而失败。

## 5. 分阶段任务

## 阶段 0：工程基线与可重复环境

### 任务 0.1：初始化后端工程

目标：建立能够被 CI 和 Docker 重复执行的 Python 工程。

主要文件：

- `backend/pyproject.toml`
- `backend/src/deeptrace/config.py`
- `backend/src/deeptrace/main.py`
- `backend/tests/unit/test_config.py`
- `.env.example`

步骤：

1. 先测试缺少必需配置时返回明确错误，测试环境允许使用 Fake Provider。
2. 创建 Settings，区分开发、测试和生产配置。
3. 添加 FastAPI 健康检查，但不加入业务接口。
4. 配置 pytest、异步测试、lint 和类型检查。
5. 验证无 API Key 时默认测试能够运行。

验收：健康检查可测试；配置不会泄露密钥；项目可以从空环境安装。

提交建议：`chore: bootstrap backend project`

### 任务 0.2：初始化数据库与 Docker Compose

目标：建立 PostgreSQL/pgvector、本地 API 和迁移基础。

主要文件：

- `docker-compose.yml`
- `backend/alembic.ini`
- `backend/migrations/`
- `backend/src/deeptrace/db/session.py`
- `backend/tests/integration/test_database.py`

步骤：

1. 先写数据库连接和 pgvector 扩展存在性测试。
2. 添加 PostgreSQL 服务、健康检查和持久化卷。
3. 建立 SQLAlchemy Session 和 Alembic 环境。
4. 添加测试数据库隔离策略。
5. 验证迁移可向前执行，并能从全新数据库启动。

验收：Docker Compose 可启动数据库；集成测试能创建并清理数据。

提交建议：`chore: add database and local infrastructure`

阶段里程碑：仓库能够安装、测试、启动，但还没有 Agent 功能。

## 阶段 1：领域模型与证据管道

### 任务 1.1：实现领域枚举与状态机

目标：先固定业务语义，再接入 LangGraph 或数据库。

主要文件：

- `backend/src/deeptrace/domain/enums.py`
- `backend/src/deeptrace/domain/models.py`
- `backend/src/deeptrace/domain/state_machine.py`
- `backend/tests/unit/domain/test_state_machine.py`

步骤：

1. 为 ResearchRun、ResearchTask、Claim 状态写允许和禁止转换测试。
2. 为 `verified`、`disputed`、`insufficient` 的发布规则写测试。
3. 实现纯 Python/Pydantic 领域对象，不依赖 ORM。
4. 为非法转换提供明确领域错误。

验收：所有状态转换具有单一入口；非法状态不能写入数据库层。

提交建议：`feat: define research domain state machine`

### 任务 1.2：实现 BudgetLedger

目标：所有模型和工具调用都受同一预算控制。

主要文件：

- `backend/src/deeptrace/services/budget.py`
- `backend/tests/unit/services/test_budget.py`

步骤：

1. 测试预算预留、实际结算、释放、超限和并发预留。
2. 实现网页数、查询数、轮次、Token、费用和截止时间限制；默认最多两轮、三个并行 Researcher、15 个网页、每个子任务三个查询和八分钟截止时间。
3. 使用幂等调用 ID，避免恢复时重复结算。
4. 定义预算不足时的结构化停止原因。

验收：并发 Researcher 不能共同突破硬预算；恢复后账本一致。

提交建议：`feat: add persistent research budget ledger`

### 任务 1.3：实现 ORM、迁移与 Repository

目标：持久化设计规范中的八个核心实体。

主要文件：

- `backend/src/deeptrace/db/models.py`
- `backend/src/deeptrace/db/repositories/`
- `backend/migrations/versions/`
- `backend/tests/integration/db/`

步骤：

1. 为 ResearchRun、Task、Source、Evidence、Claim、ClaimEvidence、Report、RunEvent 写 Repository 契约测试。
2. 实现唯一约束、外键、状态字段和必要索引。
3. Source 使用规范化 URL 与内容哈希支持去重。
4. Evidence/Claim 添加向量字段，但暂不实现召回策略。
5. 验证删除和更新不会破坏报告证据链。

验收：核心实体可事务化写入；报告引用路径可以通过单次 Repository 查询重建。

提交建议：`feat: persist research evidence graph`

### 任务 1.4：定义 Provider 契约与 Fake 实现

目标：让 Agent 逻辑与外部供应商解耦。

主要文件：

- `backend/src/deeptrace/providers/llm/base.py`
- `backend/src/deeptrace/providers/search/base.py`
- `backend/src/deeptrace/providers/fetch/base.py`
- `backend/src/deeptrace/providers/fakes/`
- `backend/tests/unit/providers/`

步骤：

1. 先写契约测试，定义成功、限流、超时、格式错误和取消语义。
2. 统一 SearchResult、FetchedDocument、ModelUsage 和 StructuredResponse。
3. Fake Provider 从 fixture 读取确定性响应，并记录调用历史。
4. 所有 Provider 接收 Cancellation 和 Budget 上下文。

验收：完整工作流能够只依赖 Fake Provider 运行；业务层不导入具体供应商 SDK。

提交建议：`feat: define agent provider contracts`

阶段里程碑：领域层、数据库和外部边界已稳定，可以开始构建真实研究纵向切片。

## 阶段 2：网页研究纵向切片

### 任务 2.1：实现安全 URL 与 Search Gateway

目标：获得去重后的搜索候选来源，并在进入网络前阻断危险地址。

主要文件：

- `backend/src/deeptrace/providers/search/gateway.py`
- `backend/src/deeptrace/security/url_policy.py`
- `backend/tests/unit/security/test_url_policy.py`
- `backend/tests/integration/providers/test_search_gateway.py`

步骤：

1. 测试私有 IP、localhost、`file://`、重定向到内网和异常 URL。
2. 测试查询限额、结果去重、主 Provider 限流和备用切换。
3. 实现 URL 规范化与 DNS/重定向后的二次校验。
4. 搜索摘要只保存在候选结果，不能构造 Evidence。

验收：危险 URL 在任何网络请求前被拒绝；Provider 切换产生可观察事件。

提交建议：`feat: add safe search gateway`

### 任务 2.2：实现 Web Fetcher 与正文抽取

目标：从公开 `text/html` 页面获得可复现的正文和元数据。

主要文件：

- `backend/src/deeptrace/providers/fetch/http_fetcher.py`
- `backend/src/deeptrace/providers/fetch/browser_fetcher.py`
- `backend/src/deeptrace/services/content_extractor.py`
- `backend/tests/fixtures/web/`
- `backend/tests/integration/fetch/`

步骤：

1. 准备静态网页、动态网页、重定向、403、大页面和注入文本 fixture。
2. 实现响应类型、大小、超时、重定向和字符集限制。
3. 普通抓取失败后按策略调用浏览器 Fetcher。
4. 提取标题、作者、发布时间、正文和可定位片段。
5. 对脚本、隐藏内容和危险标记做清理，不把网页指令传为系统消息。

验收：fixture 页面抽取稳定；失败记录结构化原因；搜索摘要不会落为 Evidence。

提交建议：`feat: fetch and extract safe web content`

### 任务 2.3：实现 Evidence 抽取与 Source 去重

目标：将网页正文转换为可验证、可定位的证据记录。

主要文件：

- `backend/src/deeptrace/services/evidence_extractor.py`
- `backend/src/deeptrace/services/source_deduplicator.py`
- `backend/tests/unit/services/test_evidence_extractor.py`
- `backend/tests/integration/services/test_source_deduplication.py`

步骤：

1. 测试原文片段、定位信息、时间字段和内容哈希。
2. 测试相同 URL、追踪参数 URL、镜像内容和页面更新。
3. Structured Output 解析失败时修复或重试一次。
4. Evidence 必须关联已经持久化的 Source 与 ResearchTask。

验收：每条 Evidence 能定位到 Source 正文；重复网页不重复计入来源覆盖率。

提交建议：`feat: extract traceable research evidence`

阶段里程碑：给定搜索查询，系统已经能安全搜索、读取和保存结构化证据。

## 阶段 3：Agent 研究闭环

### 任务 3.1：实现 Intake 与 Planner

目标：把用户问题转换为结构化 ResearchBrief 和可验收子任务。

主要文件：

- `backend/src/deeptrace/agent/state.py`
- `backend/src/deeptrace/agent/nodes/intake.py`
- `backend/src/deeptrace/agent/nodes/planner.py`
- `backend/tests/workflow/test_intake_planner.py`

步骤：

1. 用 Fake LLM 测试完整问题、不完整问题、追问一次和非法计划。
2. 定义 ResearchBrief 与 ResearchPlan Schema。
3. Planner 限制为 3～6 个子任务，并要求完成标准和优先级。
4. 计划校验失败时修复一次，仍失败则整体任务失败。

验收：相同 fixture 产生确定性合法状态；Planner 不能直接调用搜索工具。

提交建议：`feat: plan structured research tasks`

### 任务 3.2：实现 Researcher Worker

目标：并行执行 ResearchTask，但不允许 Researcher 写最终报告。

主要文件：

- `backend/src/deeptrace/agent/nodes/researcher.py`
- `backend/src/deeptrace/services/research_executor.py`
- `backend/tests/workflow/test_researcher.py`

步骤：

1. 测试查询生成、预算消耗、并发上限、局部失败和重新入队。
2. Researcher 通过 Provider 契约调用搜索、抓取和 Evidence 抽取。
3. Researcher 输出 Evidence 和候选 Claim，不输出报告段落。
4. 每次工具调用写入 RunEvent。

验收：最多三个 Researcher 并行；单个失败不会中止其他任务；预算硬限制有效。

提交建议：`feat: execute parallel research tasks`

### 任务 3.3：实现 Verifier 与 ClaimEvidence

目标：决定哪些陈述可以作为事实发布。

主要文件：

- `backend/src/deeptrace/agent/nodes/verifier.py`
- `backend/src/deeptrace/services/claim_verification.py`
- `backend/tests/unit/services/test_claim_verification.py`
- `backend/tests/workflow/test_verifier.py`

步骤：

1. 准备 supports、refutes、context、insufficient 和时间冲突 fixture。
2. 实现原子 Claim 规范化和来源独立性判断。
3. 结合确定性规则、来源质量和模型语义判断生成 ClaimEvidence。
4. 明确 `verified`、`disputed` 和 `insufficient` 的发布权限。
5. 保存 Verifier 理由的安全摘要，不保存私有思维链。

验收：没有 Evidence 路径的 Claim 永远不能发布；冲突结论保留双方证据。

提交建议：`feat: verify claims against source evidence`

### 任务 3.4：实现 Gap Controller 与停止策略

目标：根据研究缺口决定补搜、停止或部分完成。

主要文件：

- `backend/src/deeptrace/agent/nodes/gap_controller.py`
- `backend/src/deeptrace/services/coverage.py`
- `backend/tests/unit/services/test_coverage.py`
- `backend/tests/workflow/test_research_loop.py`

步骤：

1. 测试第一轮提前停止、证据不足补搜、冲突补搜、预算耗尽和无新增证据。
2. 计算子任务覆盖率、关键 Claim 来源数和新增证据收益。
3. 生成第二轮补充任务，禁止超过两轮。
4. 保存每次停止或继续的结构化原因。

验收：循环有硬终止条件；预算耗尽时进入 `partially_completed` 而不是无限等待。

提交建议：`feat: adapt research from evidence gaps`

### 任务 3.5：实现 Report Writer 与引用渲染

目标：只从发布视图生成报告。

主要文件：

- `backend/src/deeptrace/agent/nodes/report_writer.py`
- `backend/src/deeptrace/services/publication_view.py`
- `backend/src/deeptrace/services/citation_renderer.py`
- `backend/tests/workflow/test_report_writer.py`

步骤：

1. 测试 verified、disputed、insufficient 和无证据 Claim 的输出规则。
2. PublicationView 只暴露允许发布的 ClaimEvidence 数据。
3. Writer 生成摘要、发现、详细分析、冲突、不确定性和来源列表。
4. 引用映射必须可以从报告回到 Evidence 原文和 Source URL。
5. 添加“孤立引用”和“无引用事实”确定性检查。

验收：Writer 无法访问搜索摘要和原始聊天上下文；报告引用链可以重建。

提交建议：`feat: write reports from verified evidence`

### 任务 3.6：组装 LangGraph 与 Fake 端到端测试

目标：在无外部网络的情况下运行完整研究闭环。

主要文件：

- `backend/src/deeptrace/agent/graph.py`
- `backend/tests/workflow/test_research_graph.py`
- `backend/tests/fixtures/scenarios/`

步骤：

1. 为正常、提前停止、局部失败、冲突、预算耗尽和取消场景建立 fixture。
2. 组装 Intake、Planner、Researcher、Verifier、Gap Controller 和 Writer。
3. 每个 Node 前后写入 Checkpoint 和 RunEvent。
4. 验证相同 fixture 产生相同状态和引用关系。

验收：Fake 端到端研究稳定通过；核心工作流不需要 API 或前端才能运行。

提交建议：`feat: assemble deep research agent graph`

阶段里程碑：系统已经具备独立可测试的 DeepResearch 核心，是第一个可录屏的 CLI/测试演示版本。

## 阶段 4：可靠性、Memory 与 API

### 任务 4.1：实现 Checkpoint、恢复、取消与 Run Worker

目标：让长任务可以安全中断和继续。

主要文件：

- `backend/src/deeptrace/services/run_worker.py`
- `backend/src/deeptrace/services/run_service.py`
- `backend/tests/integration/services/test_run_recovery.py`

步骤：

1. 测试进程在 Researcher、Verifier 和 Writer 阶段中断后的恢复。
2. Run Worker 从数据库领取任务，避免同一 Run 被重复执行。
3. 已完成工具调用通过幂等 ID 和 BudgetLedger 避免重复计费。
4. 取消信号在模型与工具调用边界生效。

验收：中断后恢复不重复 Source/Evidence；取消后不再派发新任务。

提交建议：`feat: resume and cancel research runs`

### 任务 4.2：实现研究 Memory 与更新研究

目标：复用历史证据，同时避免误用过期信息。

主要文件：

- `backend/src/deeptrace/services/research_memory.py`
- `backend/src/deeptrace/services/freshness.py`
- `backend/tests/integration/services/test_research_memory.py`

步骤：

1. 为相似问题召回、非相似问题隔离、证据过期和页面内容变化写测试。
2. 使用 ResearchTask、Claim 和 Evidence 向量检索历史记录。
3. 按时间敏感性、发布时间、抓取时间和内容哈希分类为复用、重新验证、失效。
4. 更新研究创建子 Run，并产生新增、变化、失效和不变结论。

验收：历史 Evidence 不经时效判断不能直接发布；更新研究可复现变化来源。

提交建议：`feat: reuse and refresh research memory`

### 任务 4.3：实现 FastAPI 与 SSE

目标：提供提交、查看、取消、恢复和更新研究的稳定接口。

主要文件：

- `backend/src/deeptrace/api/routes/runs.py`
- `backend/src/deeptrace/api/routes/reports.py`
- `backend/src/deeptrace/api/sse.py`
- `backend/tests/integration/api/`

步骤：

1. 先写 API 契约测试和 SSE 断线重连测试。
2. 实现创建、读取、取消、恢复、更新研究和获取报告接口。
3. SSE 使用持久化 RunEvent 游标，重连后补发遗漏事件。
4. 错误响应不包含密钥、内部 Prompt 或完整模型上下文。

验收：API 重启后客户端可以继续读取任务状态；重复请求具有合理幂等语义。

提交建议：`feat: expose research run api and events`

### 任务 4.4：实现最小 Web UI

目标：完成可演示的用户流程，不制作复杂管理后台。

主要文件：

- `frontend/src/pages/NewResearch.tsx`
- `frontend/src/pages/ResearchRun.tsx`
- `frontend/src/pages/Report.tsx`
- `frontend/src/components/`
- `frontend/tests/`

步骤：

1. 测试提交问题、确认 ResearchBrief、查看进度、取消和打开引用。
2. 实现问题输入和最多一次澄清交互。
3. 实时展示阶段、查询、来源、失败、Token、费用和耗时。
4. 报告支持行内引用，点击后显示 Source 与 Evidence 原文片段。
5. 明确展示部分完成、冲突和研究缺口。

验收：用户可以从提交问题走到查看证据报告；UI 不展示私有思维链。

提交建议：`feat: add deep research web experience`

阶段里程碑：完成真实用户可使用的部署形态，并具备中断恢复和更新研究。

## 阶段 5：安全与可观测性

### 任务 5.1：补全 Prompt Injection 与 SSRF 防护

目标：用可执行测试证明网页不能控制 Agent 或访问内网。

主要文件：

- `backend/src/deeptrace/security/content_policy.py`
- `backend/tests/security/test_prompt_injection.py`
- `backend/tests/security/test_ssrf.py`
- `backend/tests/fixtures/security/`

步骤：

1. 创建包含“忽略系统指令”、伪工具结果、密钥诱导和隐藏文本的网页。
2. 验证网页内容只作为数据进入 Evidence Extractor。
3. 覆盖 IPv4/IPv6、DNS 重绑定、重定向和特殊 URL 编码。
4. 前端引用和 RunEvent 通过 XSS fixture 验证转义。

验收：安全 fixture 不能改变工具权限、泄露配置或访问私有地址。

提交建议：`security: harden untrusted research content`

### 任务 5.2：实现 Tracing 与运行指标

目标：让每次研究可调试、可比较、可计算成本。

主要文件：

- `backend/src/deeptrace/observability/tracing.py`
- `backend/src/deeptrace/observability/metrics.py`
- `backend/tests/integration/observability/`

步骤：

1. 为 Agent Node、LLM、搜索、抓取和数据库阶段定义 Span 属性。
2. Token、费用、重试、缓存命中和 Evidence 产出进入指标。
3. 敏感字段默认不记录，Prompt/正文采样需要显式开启。
4. 实现按 Run 导出的调试摘要。

验收：可以定位最慢和最贵的步骤；日志中不出现 API Key。

提交建议：`feat: trace agent quality cost and latency`

阶段里程碑：系统具备生产型 Agent 的安全与诊断基础。

## 阶段 6：评测、消融与作品集交付

### 任务 6.1：建立 30 题中文评测集

目标：形成可复现、不会泄漏隐藏集答案的评测资产。

主要文件：

- `evals/datasets/deeptrace_dev.jsonl`
- `evals/datasets/deeptrace_holdout.jsonl`
- `evals/fixtures/snapshots/`
- `evals/README.md`

步骤：

1. 每类编写五题，并标注时间敏感性、期望来源类型和核心子问题。
2. 划分 20 题开发集与 10 题隐藏集。
3. 动态问题保存评测时间、网页快照和来源许可说明。
4. 不把人工参考答案传给被测 Agent。

验收：每题都有明确评分依据；隐藏集不参与 Prompt 调试。

提交建议：`test: add Chinese deep research benchmark`

### 任务 6.2：实现确定性指标与 Judge 接口

目标：统一计算质量、成本和延迟。

主要文件：

- `backend/src/deeptrace/evaluation/metrics.py`
- `backend/src/deeptrace/evaluation/judges.py`
- `backend/tests/unit/evaluation/`
- `evals/run_evaluation.py`

步骤：

1. 测试 Citation Validity、Completeness、来源独立性和成本指标。
2. 定义 Claim–Evidence 支持判断和 Coverage Judge 契约。
3. Judge 结果保存模型、版本、Prompt 哈希和原始评分。
4. 支持人工复核覆盖 Judge 结果，但保留变更记录。

验收：同一实验可以重复计算；确定性指标不依赖 Judge 模型。

提交建议：`feat: evaluate research quality and cost`

### 任务 6.3：实现 Baseline 与消融配置

目标：证明 Multi-Agent、Verifier、Gap Controller 和 Memory 的实际价值。

主要文件：

- `evals/baselines/direct_answer.py`
- `evals/experiments/`
- `evals/configs/`

步骤：

1. 实现单次搜索加直接回答基线。
2. 通过配置关闭并行 Researcher、Verifier 和自适应停止。
3. 在小规模题集上调用 GPT Researcher/Open Deep Research，保留版本和配置。
4. 所有实验使用相近模型、搜索与成本预算，无法对齐时明确记录。
5. 单独运行首次研究与更新研究的 Memory 实验。

验收：至少三组消融可以一条命令运行；结果同时包含质量与成本。

提交建议：`feat: add agent baselines and ablations`

### 任务 6.4：生成评测报告

目标：把真实结果转化为可面试讲解的技术结论。

主要文件：

- `evals/results/`
- `docs/evaluation-report.md`

步骤：

1. 运行开发集，固定版本后再运行隐藏集。
2. 人工抽查隐藏集 Claim–Evidence 支持关系。
3. 对失败案例按规划、搜索、抓取、验证、写作和预算分类。
4. 生成完整版与消融版的质量、成本和延迟对比。
5. 不修改未达标数据，只记录原因和下一步优化。

验收：报告能够回答“哪个机制提升了什么、代价是什么、失败在哪里”。

提交建议：`docs: report DeepTrace evaluation results`

### 任务 6.5：完成作品集交付

目标：让面试官可以快速理解、运行和验证项目。

主要文件：

- `README.md`
- `docs/demo-script.md`
- `docs/resume-bullets.md`
- `.github/workflows/ci.yml`

步骤：

1. README 说明问题、架构、证据链、Memory、评测结果和复现方式。
2. Docker Compose 一条命令启动，示例配置不包含密钥。
3. CI 运行确定性测试、静态检查和前端构建。
4. 录制 3～5 分钟演示：招聘调研、证据展开、更新研究和执行轨迹。
5. 简历描述只使用真实实现和真实数据。

验收：新用户按 README 可以启动 Fake Demo；有 API Key 时可以运行真实研究。

提交建议：`docs: prepare DeepTrace portfolio release`

阶段里程碑：项目达到可投递、可演示、可复现实验的状态。

## 6. 周期安排

| 周次 | 目标 | 可交付结果 |
|---|---|---|
| 第 1 周 | 阶段 0～1 | 工程基线、领域模型、数据库、Provider Fake |
| 第 2 周 | 阶段 2 | 真实搜索、网页抓取、Evidence 管道 |
| 第 3 周 | 阶段 3 | 完整 Agent 闭环与 Fake 端到端测试 |
| 第 4 周 | 阶段 4 | 恢复、Memory、API、最小 UI |
| 第 5 周 | 阶段 5 与评测框架 | 安全、Tracing、30 题数据集和指标 |
| 第 6 周 | 消融与交付 | 评测报告、README、部署和演示视频 |

如果只有四周，优先保留阶段 0～3、API、最小 UI 和 10 题评测；将长期 Memory、备用浏览器抓取和完整 30 题实验延后，但不能删除 Evidence/Verifier、预算控制和引用评测。这个四周版本只是可投递核心版，不视为设计规范中的完整 MVP；补齐延后项后才通过最终发布门禁。

## 7. 关键依赖顺序

```text
领域模型 ─┬─> ORM/Repository ──────────────┐
          └─> BudgetLedger                │
Provider 契约 ─> Search/Fetch/Evidence ───┤
                                           v
Intake/Planner -> Researcher -> Verifier -> Gap Controller -> Writer
                                           │
                                           v
Checkpoint/Worker -> API/SSE -> Web UI -> Evaluation
                         │
                         └─> Memory/Update Research
```

不得在 Evidence 管道和 Fake Provider 稳定前开始复杂 UI；不得在确定性工作流测试通过前运行大规模真实模型评测。

## 8. 风险与控制

### 8.1 外部 API 成本失控

- 默认开发使用 Fake Provider。
- 真实 E2E 使用独立标记和显式环境开关。
- BudgetLedger 在调用前预留预算。
- 大规模评测先运行一题成本预估。

### 8.2 网页不稳定导致测试抖动

- 工作流测试全部使用 fixture。
- 真实 E2E 只验证结构和阈值，不比较完整文本。
- 动态评测保存时间与网页快照。

### 8.3 Multi-Agent 只增加复杂度

- Researcher 只负责明确子任务。
- 最多三个并行 Worker、两轮研究。
- 使用单 Agent 与无 Verifier 消融证明价值。

### 8.4 前端消耗过多时间

- 只实现提交、进度、报告、证据抽屉和历史任务。
- 不做登录、权限、富文本编辑和复杂管理后台。

### 8.5 指标被 Judge 偏差污染

- 优先使用确定性引用和成本指标。
- 保存 Judge 配置与原始分数。
- 隐藏集进行人工抽查。

## 9. 每阶段完成定义

一项任务只有同时满足以下条件才可标记完成：

- 新行为有测试覆盖，目标测试先失败后通过。
- 相关测试、lint 和类型检查通过。
- 错误信息和运行事件不泄露敏感数据。
- 对外接口和数据模型与设计规范一致。
- 没有未说明的临时空实现或跳过测试。
- 形成一个聚焦的 Git 提交。

## 10. 最终发布门禁

发布前必须确认：

- 设计规范中的 MVP 功能均已实现或明确标为未完成。
- 引用可访问率、支持率、覆盖率、无来源事实率和任务成功率使用真实数据。
- Prompt Injection 和 SSRF 测试通过。
- 至少三组消融实验完成。
- Docker Compose、Fake Demo 和真实研究路径均有文档。
- 仓库不包含 API Key、私有 Prompt 日志或受限网页全文。
- 简历与 README 中没有无法由代码、测试或实验结果支持的表述。
