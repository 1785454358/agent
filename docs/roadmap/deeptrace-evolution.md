# DeepTrace 演进路线图

- 状态　阶段 1、2、3 已完成；阶段 4 实现与自动化验证完成，真实端到端门禁待通过
- 更新日期　2026-09-02
- 目标　从 CLI 单 Agent 演进为具备上下文压缩、可靠抓取、证据验证、记忆、产品化与系统评测能力的 Deep Research Agent
- 当前阶段设计　[阶段 4 Evidence Store 与 Verifier](../superpowers/specs/2026-09-01-stage-04-evidence-verification-design.md)
- 模块化设计　[DeepTrace 模块化目录重构](../superpowers/specs/2026-08-31-deeptrace-module-layout-design.md)

## 1. 后续开发方式

阶段 1 已经跑通真实 LLM、Tavily 搜索和网页抓取的单 Agent 闭环。从阶段 2 开始，Codex 直接在 `backend/` 中实现代码，不再生成隔离参考项目，也不再要求学习者手动复制参考代码。

阶段 2 代码已经按业务能力整理为 models、prompts、config、context、tools、observability、orchestration 和 agent 子包。后续模块只在对应阶段实现时创建，不预留空目录。

代码保留必要的中文注释。文档简洁说明每个文件和函数的职责，对 LangGraph 状态流转、上下文压缩、Evidence Store、Verifier 等核心机制展开说明。每阶段只做保证功能可靠所需的测试和真实冒烟验证。固定数据集、消融及开源项目大规模对比统一放到阶段 6。

## 2. 六阶段总览

| 阶段 | 核心能力 | 可验证产物 | 岗位能力 |
|---|---|---|---|
| 1 | CLI 单 Agent、搜索、抓取 | 真实两工具闭环 | Tool Calling、Agent loop |
| 2 | LangGraph、上下文压缩、可靠抓取 | 压缩笔记、逐轮 Token 统计、抓取降级链 | 状态编排、RAG、工具工程 |
| 3 | 规划式 Deep Research | Planner、Researcher、Writer、查询扩展、批量抓取与覆盖状态 | 规划执行、专业领域 Agent |
| 4 | Evidence Store 与 Verifier | Claim 级引用、可靠性验证、证据驱动补搜与动态停止 | 数据建模、可追溯性、评估 |
| 5 | Memory 与产品化 | 记忆、持久化、API、Web UI 与任务可观测性 | Memory 机制、AI 应用落地 |
| 6 | 系统评测与开源对比 | 固定数据集、消融、基线对比 | 评估体系、开源复现 |

## 3. 阶段 1 CLI 单 Agent

阶段 1 已完成 CLI、`search_web`、`fetch_webpage` 和真实 Tool Calling 闭环。当前暴露出三个问题。

- 整页正文持续进入对话，上下文随研究轮次快速膨胀。
- HTTPX 与 Trafilatura 无法稳定处理 JavaScript 页面和提取失败页面。
- 手写循环缺少显式状态、节点边界与可扩展编排结构。

## 4. 阶段 2 LangGraph 编排、上下文压缩与可靠抓取

### 目标

将单 Agent 迁移到 LangGraph。网页正文经过本地 BGE-M3 召回和 LLM 压缩后形成研究笔记，不再直接进入主 Agent 对话。抓取增加降级链，每轮输出压缩前后的 Token 估算。

```text
用户问题 → Agent → 搜索 → 选择网页 → 并发抓取
        → 分块与 BGE-M3 批量向量化
        → 双查询筛选 → 并发压缩为 ResearchNote
        → 按 tool_call_id 回填 → Agent 继续研究或回答
```

### 主要实现

- LangGraph 表达 Agent、工具、压缩、回填和终止节点。
- State 只保存可序列化文本和元数据。向量放在单次运行的 `CompressionRuntime`，不进入 checkpoint。
- 网页按约 800 token 分块、重叠 100 token。相关性使用 `score = max(sim(user_query, chunk), sim(active_query, chunk))`。
- 初始取约 6 个块并扩展相邻块。融合 top-1 低于 `0.45` 时标记整页不相关，跳过压缩调用。
- ResearchNote 检索也采用双查询 max 融合，代表文本由标题、要点和证据摘录组成。
- 结构化压缩失败时依次执行 JSON 修复、一次重试和抽取式降级。
- 多页压缩使用有界并发，结果按原始顺序和 `tool_call_id` 回填。
- 抓取链为 HTTPX + Trafilatura、同一 HTML 的 BeautifulSoup、Playwright 渲染后再提取。正文少于 500 字符或 200 token 时进入下一级，并记录 `scraper_used`。
- URL 使用抓取前保守规范化和抓取后内容身份确认。重复页面遇到新子问题时复用正文、chunks 和向量，只重新筛选。
- 初期保留最多 8 步，随后启用软上限 8、硬上限 12、最多延长一次。新查询与历史查询最大相似度超过 `0.85` 时拒绝延长。

### Token 节省统计

阶段 2 只做运行观测，不做大规模效果评测。每轮记录以下数据。

- `estimated_baseline_context_tokens`，假设沿用阶段 1，把截至当前轮的网页正文全部留在对话中的 Token 数。
- `estimated_actual_context_tokens`，当前真正构造给主 Agent 的有界上下文估算值。
- `estimated_gross_saved_tokens`，基线减去实际上下文。
- `compression_input_tokens`、`compression_output_tokens`，本轮压缩模型消耗。
- `estimated_net_saved_tokens`，毛节省减去压缩调用消耗。
- 毛节省率、净节省率和累计值。
- Provider 返回 usage 时另行展示真实 prompt/completion usage，不与本地估算混用。

统一使用可配置的 `cl100k_base` 做对照估算，结果标记为估算。BGE-M3 的向量计算量属于本地工作量，不计作 API Token。

### 阶段门禁

- 阶段 1 的真实问题仍能完成搜索、抓取和最终回答。
- 主 Agent 对话中不存在整页正文，只保留研究笔记和必要元数据。
- 静态页面和至少一个浏览器降级页面有可解释结果。
- 压缩失败、单页失败和并发乱序不会破坏其他结果，`tool_call_id` 始终正确。
- CLI 展示每轮及累计的基线、实际值、毛节省和净节省。
- 必要单元测试和一次真实端到端冒烟测试通过。

本阶段不拆分 Planner、Researcher、Writer，不实现 Evidence Store、Verifier、长期 Memory、数据库、API 或 Web UI，也不运行固定问题集、消融和开源项目横向对比。

## 5. 阶段 3 规划式 Deep Research

在阶段 2 的 LangGraph 上拆出 Planner、Researcher 与 Writer，形成清晰的“规划 → 分项研究 → 汇总写作”流水线。吸收 GPT Researcher 先规划、按子问题检索、研究完成后统一写报告的优点，但不照搬其缺少时间约束、来源质量控制和证据验证的问题。

### 主要实现

- Planner 先规范化用户问题，修复多余空格等查询噪声，并提取语言、时间范围和输出要求。
- Planner 输出结构化 `ResearchPlan`，将宽泛问题拆为互补的研究维度。例如技术突破、产品与框架、行业落地、市场与公司布局、风险与局限。
- 每个子任务包含 `section_id`、研究问题、搜索查询、时间范围、期望来源类型、最低来源要求和预期产物，避免只生成若干无约束的相似查询。
- Researcher 按子任务执行搜索、抓取、召回和压缩，不直接负责完整报告写作；每个子任务输出独立 `SectionResult` 和覆盖状态。
- Researcher 围绕子任务生成和执行查询，进行查询规范化、历史去重以及有界批量抓取。BGE-M3 继续按用户问题和当前子问题融合召回。
- 阶段 3 使用研究笔记数、成功来源数和任务预期要点建立基础覆盖状态；尚不做 Claim 级证据判断。
- 调度器综合任务完成状态、连续无新增笔记以及网页、步骤、Token、费用和时间预算决定继续、切换子任务或写作。
- Writer 只消费研究计划、研究笔记和子任务状态。默认生成摘要、分层正文、必要的对比表、局限说明和来源列表，不在写作阶段偷偷发起新搜索。
- 个别子任务失败时保留原因，Writer 可以生成标明缺口的部分报告，不能用流畅措辞掩盖资料不足。

### 阶段门禁

- 一个宽泛真实问题能够被拆成不重复、可解释的研究子任务。
- Planner、Researcher、Writer 的输入输出模型和 LangGraph 状态流转清晰。
- 写作阶段不会接收整页正文，也不会越权调用搜索和抓取工具。
- 多个子任务能够依次完成搜索、批量抓取、压缩和基础覆盖更新，重复查询不会形成无限循环。
- 报告能显示已完成、证据不足和执行失败的研究部分。

## 6. 阶段 4 Evidence Store 与 Verifier

把证据建模、可靠性验证和证据驱动补搜放在同一个闭环中，形成 DeepTrace 的核心差异化能力。

### Evidence Store

- 建立 `Source → Evidence → Claim` 数据链，使任意确定事实可以回溯到真实网页和原文位置。
- 记录 `query`、`section_id`、来源渠道、来源类型、发布机构、抓取方式、内容哈希和抓取时间。
- 区分 `publication_date` 与 `event_date`，防止时间范围污染。
- 保存证据摘录、原文位置和 `claim_id`；来源列表只包含报告实际使用的来源。

### Verifier 与研究反馈

- 检查引用覆盖、证据蕴含、时间边界、来源质量、关键数字和来源冲突。
- 官方公告、论文、产品文档和监管材料优先；低质量来源不能单独支撑高风险结论。
- 重要金额、比例、性能和市场规模检查单位、口径、时间范围及原文支持。
- 未验证、冲突未解决、来源过弱或过期的 Claim 必须降级、标记不确定或移除。
- 将证据缺口和冲突转为结构化补搜任务，返回 Researcher；按来源配额补足来源多样性。
- 综合 Claim 覆盖率、验证状态、连续无新增证据以及时间、网页、Token 和费用预算动态停止。
- Writer 只能把验证通过的 Claim 写成确定事实。

本阶段只用少量真实案例验证数据链、判定和补搜闭环。规模化准确率与消融放到阶段 6。

当前代码、定向集成、非真实套件、锁文件和编译检查均已完成。增加单次 60 秒模型调用边界后，真实 LLM、Tavily、网页抓取和本地 BGE-M3 冒烟已两次到达 Writer。小型单任务运行得到 3 个来源、17 条 Evidence（13 条精确定位）和 16 个 Claim；Claim Extractor/Verifier 未在时限内返回合格结果，全部 Claim 降级为 `partially_supported`，报告状态为 `partial`。由于没有 `verified` Claim，本阶段真实门禁仍未通过。

## 7. 阶段 5 Memory 与产品化

这一阶段共用任务身份、持久化和生命周期设计，分三个任务组实施。

### Memory 与持久化

- 增加会话记忆、研究记忆和用户偏好。
- 研究记忆只复用带来源、验证状态、事件时间、发布时间、更新时间与适用范围的信息。
- 记忆检索继承当前子任务和时间范围，时间敏感证据复用前重新验证。
- 增加 LangGraph checkpoint、任务恢复和持久化存储。
- 禁止保存私有思维链和未经验证的对话全文。

### API 与任务管理

- FastAPI 提供任务创建、查询、取消、恢复和结果接口。
- 后台任务具有稳定 ID、状态、预算、错误和终止原因。
- SSE 推送规划、搜索、抓取、召回、验证、写作和完成事件。

### Web UI 与可观测性

- Web UI 展示研究计划、子任务覆盖、抓取成功与失败、来源、证据、Verifier 结果、报告和停止原因。
- 记录分阶段 Token、模型费用、搜索费用、耗时和总成本。
- 完成日志、指标、权限边界与凭据保护。

## 8. 阶段 6 系统评测与开源对比

系统稳定后建立固定中文评测集、配置哈希、原始结果归档和人工抽查。内部基线与消融覆盖阶段 1 单 Agent、阶段 2 上下文压缩与可靠抓取、阶段 3 规划式研究、阶段 4 证据验证以及阶段 5 Memory。

评测报告研究覆盖率、事实正确率、Claim 级引用正确率、来源权威性与多样性、时间边界正确率、数字验证结果、抓取成功率、失败恢复、时延、Token 和费用。报告形式和篇幅不能替代事实与证据质量评分。

首批外部基线包括 [Open Deep Research](https://github.com/langchain-ai/open_deep_research) 和 [GPT Researcher](https://github.com/assafelovic/gpt-researcher)。对比时固定 Git commit、模型、问题集、搜索与网页预算、时间窗口和成本口径。保存计划、查询、抓取记录、实际引用来源、运行时间和费用；无法对齐的条件如实说明，不可用结果标为 `unavailable`。

## 9. 全局阶段门禁

1. 必要自动化测试通过，上一阶段核心行为没有回退。
2. 至少一个真实场景完整运行，外部限制导致失败时保留可解释原因。
3. 新增状态、接口和算法有简洁中文说明，核心机制可以被学习者解释。
4. 代码直接进入正式 `backend/`，包含必要中文注释，不再维护隔离参考实现。
5. 不使用 Fake、静态结果或手工修改输出冒充真实验收。
6. Git 提交不包含 API Key、Cookie、Token 或敏感请求头。
7. 阶段 1 至 5 不做大规模评测，运行日志和小型功能验证只用于保证系统正常工作。

## 10. 当前下一步

在能于 60 秒时限内返回结构化 Claim 与验证结果的真实 Provider 环境中重新运行阶段 4 冒烟，确认至少一个 `verified` Claim、必要的数字检查、有界补搜行为和 Writer Claim 级引用。通过该门禁后才能开始阶段 5；此前不实现 Memory、API、Web UI 或规模化评测。
