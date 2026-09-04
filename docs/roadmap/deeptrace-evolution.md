# DeepTrace 演进路线图

- 状态　阶段 1、2、3 已完成；阶段 4（Evidence/Claim/Verifier）已移除；阶段 5（Memory 与产品化）已完成；阶段 6 未开始
- 更新日期　2026-09-03
- 目标　从 CLI 单 Agent 演进为具备上下文压缩、可靠抓取、记忆、产品化与系统评测能力的 Deep Research Agent
- 当前能力　阶段 1-3 的规划式研究链路 + 阶段 5 的 Memory/API/Web UI，详见[后端运行说明](../backend/README.md)
- 模块化设计　[DeepTrace 模块化目录重构](../superpowers/specs/2026-08-31-deeptrace-module-layout-design.md)

## 1. 后续开发方式

阶段 1 已经跑通真实 LLM、Tavily 搜索和网页抓取的单 Agent 闭环。从阶段 2 开始，Codex 直接在 `backend/` 中实现代码，不再生成隔离参考项目，也不再要求学习者手动复制参考代码。

阶段 2 代码已经按业务能力整理为 models、prompts、config、context、tools、observability、orchestration 和 agent 子包。后续模块只在对应阶段实现时创建，不预留空目录。

代码保留必要的中文注释。文档简洁说明每个文件和函数的职责，对 LangGraph 状态流转、上下文压缩、零 LLM 压缩笔记与 Writer 机械引用等核心机制展开说明。每阶段只做保证功能可靠所需的测试和真实冒烟验证。固定数据集、消融及开源项目大规模对比统一放到阶段 6。

## 2. 六阶段总览

| 阶段 | 核心能力 | 可验证产物 | 岗位能力 |
|---|---|---|---|
| 1 | CLI 单 Agent、搜索、抓取 | 真实两工具闭环 | Tool Calling、Agent loop |
| 2 | LangGraph、上下文压缩、可靠抓取 | 压缩笔记、逐轮 Token 统计、抓取降级链 | 状态编排、RAG、工具工程 |
| 3 | 规划式 Deep Research | Planner、Researcher、Writer、查询扩展、批量抓取与覆盖状态 | 规划执行、专业领域 Agent |
| 5 | Memory 与产品化 | 研究记忆、任务管理 API、SSE、持久化与 Web 仪表盘 | Memory 机制、AI 应用落地 |
| 6 | 系统评测与开源对比 | 固定数据集、消融、基线对比 | 评估体系、开源复现 |

阶段 4（原计划 Evidence Store 与 Verifier）已于 2026-09-03 移除，阶段 5、6 沿用原编号。

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

## 6. 阶段 4 Evidence Store 与 Verifier（已移除）

原计划把证据建模、可靠性验证和证据驱动补搜放入同一闭环，形成 Claim 级可追溯与验证能力。该方向已于 2026-09-03 经项目所有者决策移除。

- 移除原因：Claim 抽取与核验会让同一内容被 LLM 重复读取约 3 遍（占 Token 约 40%），且在真实 Provider 时限内从未产出可用的 `verified` 结论，收益无法覆盖成本。
- 处置：Writer 改为直接基于带编号来源的原文片段写作，引用由系统机械拼接、模型无法伪造出处；对应源码、测试与设计文档归档为废弃历史（见 [docs/README](../README.md) 的"已移除阶段资料"）。
- 保留能力：阶段 3 质量加固已包含的时间关系分类（`in_range` / `retrospective` / `unknown` / `out_of_range`）、来源质量与低质提示、数字核验提示等确定性规则仍保留在压缩与笔记层，但它们只是流程质量判断，不构成 Claim 级验证结论。

## 7. 阶段 5 Memory 与产品化

已实现（2026-09-03）：研究记忆、任务管理 API、SSE 事件流、运行持久化与 Web 仪表盘，与阶段 3 研究链路构成当前系统。

### Memory 与持久化（已完成）

- 研究记忆（`DEEPTRACE_USE_MEMORY`）：成功抓取的页面按 URL 与内容哈希写入 `memory/notes.jsonl`；后续运行命中同一 URL 时免网络抓取（不占页面预算），直接进入召回与压缩。
- 记忆保存一手页面正文与来源 URL、标题、发布时间、抓取时间；运行记录持久化为 `runs/<id>.json`。
- 会话记忆、用户偏好、LangGraph checkpoint 与任务恢复未实现，保留为后续扩展。

### API 与任务管理（已完成）

- FastAPI 提供任务创建、列表、查询、取消与结果接口；后台任务具有稳定 ID、状态、预算、错误和终止原因。
- SSE 推送规划、搜索、抓取、压缩、写作与完成事件。
- 任务恢复接口未实现。

### Web UI 与可观测性（已完成）

- 仪表盘输入问题后实时展示事件流，完成后轮询展示最终报告与来源数量。
- 记录并展示分阶段 Token、按角色用量与估算模型费用（价格未配置时显示 unavailable）。
- 权限边界与凭据保护未实现；API Key 等敏感信息不写入日志、文档或 Git。

## 8. 阶段 6 系统评测与开源对比

系统稳定后建立固定中文评测集、配置哈希、原始结果归档和人工抽查。内部基线与消融覆盖阶段 1 单 Agent、阶段 2 上下文压缩与可靠抓取、阶段 3 规划式研究以及阶段 5 Memory 产品化链路。

评测报告研究覆盖率、来源权威性与多样性、时间边界正确率、抓取成功率、失败恢复、时延、Token 和费用。报告形式和篇幅不能替代事实与来源质量评分。

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

阶段 4 已移除、阶段 5 已落地，当前系统 = 阶段 3 规划式研究 + 阶段 5 产品化外壳。进入阶段 6 前先用真实问题回归 CLI 与 API 端到端路径（`completed`/`partial`/`failed` 状态与非零退出码行为），确认在移除 Claim 层后 Writer 的机械引用与来源列表仍正确。规模化评测是阶段 6 范围，开始前不提前实现评测平台或数据库持久化。
