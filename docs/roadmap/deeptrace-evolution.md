# DeepTrace 演进路线图

- 状态　阶段 1 已完成，阶段 2 设计已确认
- 更新日期　2026-08-30
- 目标　从 CLI 单 Agent 演进为具备上下文压缩、可靠抓取、证据验证、记忆、产品化与系统评测能力的 Deep Research Agent
- 总体设计　[DeepTrace 从零演进式构建设计](../superpowers/specs/2026-08-29-deeptrace-evolution-design.md)
- 当前设计　[阶段 2 LangGraph 编排、上下文压缩与可靠抓取](../superpowers/specs/2026-08-30-stage-02-langgraph-context-compression-design.md)

## 1. 后续开发方式

阶段 1 已经跑通真实 LLM、Tavily 搜索和网页抓取的单 Agent 闭环。从阶段 2 开始，Codex 直接在 `backend/` 中实现代码，不再生成隔离参考项目，也不再要求学习者手动复制参考代码。

代码保留必要的中文注释。文档简洁说明每个文件和函数的职责，对 LangGraph 状态流转、上下文压缩、Evidence Store、Verifier 等核心机制展开说明。每阶段只做保证功能可靠所需的测试和真实冒烟验证。固定数据集、消融及开源项目大规模对比统一放到阶段 9。

## 2. 九阶段总览

| 阶段 | 核心能力 | 可验证产物 | 岗位能力 |
|---|---|---|---|
| 1 | CLI 单 Agent、搜索、抓取 | 真实两工具闭环 | Tool Calling、Agent loop |
| 2 | LangGraph、上下文压缩、可靠抓取 | 压缩笔记、逐轮 Token 统计、抓取降级链 | 状态编排、RAG、工具工程 |
| 3 | Agent 模块拆分 | Planner、Researcher、Writer | 规划执行、系统设计 |
| 4 | Evidence Store | Claim、Evidence、Source 可追踪 | 数据建模、可追溯性 |
| 5 | Verifier | 引用覆盖、蕴含、冲突、时效检查 | 可靠性与评估 |
| 6 | Memory | 会话记忆、研究记忆、用户偏好 | Memory 机制 |
| 7 | Deep Research 强化 | 查询改写、停止条件、并发与预算 | 专业领域 Agent |
| 8 | 产品化 | API、Web UI、任务状态与可观测性 | AI 应用落地 |
| 9 | 系统评测与开源对比 | 固定数据集、消融、基线对比 | 评估体系、开源复现 |

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

## 5. 阶段 3 Agent 编排与模块拆分

在阶段 2 的 LangGraph 上拆出 Planner、Researcher 与 Writer。Planner 生成结构化研究计划，Researcher 发现和压缩信息，Writer 只消费研究笔记。失败任务保留明确状态并允许生成部分报告。本阶段只验证模块契约、状态流转和真实闭环。

## 6. 阶段 4 Evidence Store

建立 `Source → Evidence → Claim` 数据链，保留 URL、抓取时间、正文定位、证据文本和 Claim 关联。任意确定事实可以回溯到实际抓取来源。本阶段以结构正确、可导出和真实案例可追溯为门禁，不提前设规模化指标。

## 7. 阶段 5 Verifier

增加引用覆盖、证据蕴含、来源冲突、来源质量和时效检查。Verifier 输出结构化判定和待修复项，不修改原始证据。未验证、冲突未解决或过期的 Claim 不能作为确定事实发布。规模化准确率及消融留到阶段 9。

## 8. 阶段 6 Memory

增加会话记忆、研究记忆和用户偏好。研究记忆只复用带来源、验证状态、更新时间与适用范围的信息，时间敏感证据复用前重新验证。禁止保存私有思维链和未经验证的对话全文。本阶段只验证首次研究、后续更新和失效处理。

## 9. 阶段 7 Deep Research 强化

增加查询改写、来源多样化、覆盖缺口补搜、有界并发和预算停止条件。达到时间、网页、Token 或费用预算时生成明确的部分报告。本阶段验证预算与停止机制，策略质量和成本收益对比留到阶段 9。

## 10. 阶段 8 产品化

FastAPI 提供任务创建、查询、取消和结果接口，SSE 推送安全运行事件。Web UI 展示计划、状态、来源、证据、Verifier 结果和报告。实现 checkpoint、恢复、日志、指标与凭据保护。

## 11. 阶段 9 系统评测与开源对比

系统稳定后建立固定中文评测集、配置哈希、原始结果归档和人工抽查。内部基线与消融覆盖阶段 1 单 Agent、上下文压缩、双查询召回、浏览器降级、Evidence Store、Verifier、Memory 和动态停止。评测同时报告质量、引用、覆盖、来源质量、时效、成功率、时延、Token、费用和失败恢复。

首批外部基线包括 [Open Deep Research](https://github.com/langchain-ai/open_deep_research) 和 [GPT Researcher](https://github.com/assafelovic/gpt-researcher)。对比时固定 Git commit、模型、问题集、搜索与网页预算、时间窗口和成本口径。无法对齐的条件必须如实说明，不可用结果标为 `unavailable`。

## 12. 全局阶段门禁

1. 必要自动化测试通过，上一阶段核心行为没有回退。
2. 至少一个真实场景完整运行，外部限制导致失败时保留可解释原因。
3. 新增状态、接口和算法有简洁中文说明，核心机制可以被学习者解释。
4. 代码直接进入正式 `backend/`，包含必要中文注释，不再维护隔离参考实现。
5. 不使用 Fake、静态结果或手工修改输出冒充真实验收。
6. Git 提交不包含 API Key、Cookie、Token 或敏感请求头。
7. 阶段 1 至 8 不做大规模评测，运行日志和小型功能验证只用于保证系统正常工作。

## 13. 当前下一步

确认阶段 2 正式设计后生成实施计划。实施时直接修改 `backend/`，按测试驱动方式完成 LangGraph 迁移、BGE-M3 压缩、抓取降级链和逐轮 Token 统计。
