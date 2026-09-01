# DeepTrace 阶段 3

DeepTrace 是命令行规划式深度研究 Agent。Planner 先把宽泛问题拆成结构化子任务，Researcher 逐任务调用搜索和网页抓取，整页正文经过本地 BGE-M3 召回与 LLM 压缩后形成 ResearchNote，Writer 最后只基于计划、笔记和章节覆盖状态统一写作。

## 运行

复制 `.env.example` 为 `.env`，填写真实 OpenAI-compatible 接口和 Tavily Key：

```powershell
uv sync
uv run playwright install chromium
uv run deeptrace "今天 AI Agent 领域有哪些热点新闻？"
```

Chromium 只在 HTTPX 无法提取足够正文时启用。受控代理或沙箱把公网域名映射到 `198.18.0.0/15` 时，可以显式设置 `DEEPTRACE_ALLOW_BENCHMARK_DNS_PROXY=true`；普通网络环境不要开启。

阶段 3 的主要预算环境变量及默认值如下：

```text
DEEPTRACE_MAX_RESEARCH_TASKS=4
DEEPTRACE_MAX_TASK_ROUNDS=3
DEEPTRACE_MIN_SOURCES_PER_TASK=2
DEEPTRACE_MAX_FETCHED_PAGES=20
DEEPTRACE_MAX_RUNTIME_SECONDS=600
DEEPTRACE_MAX_API_TOKENS=120000
DEEPTRACE_WRITER_TOKEN_RESERVE_RATIO=0.15
```

可选的 `DEEPTRACE_INPUT_COST_PER_MILLION`、`DEEPTRACE_OUTPUT_COST_PER_MILLION` 和 `DEEPTRACE_MAX_COST_USD` 用于费用估算及上限；设置费用上限时必须同时提供输入、输出单价。

## 目录结构

```text
src/deeptrace/
├── agent/             # Planner、Researcher、Writer、Agent 门面与真实依赖组装
├── config/            # 环境变量、默认值和配置校验
├── context/           # 分块、BGE-M3、召回与压缩
├── models/            # 计划、覆盖状态、章节、研究笔记与指标模型
├── observability/     # Token 估算、账本和格式化
├── orchestration/     # LangGraph State、任务调度、预算、工具执行与拓扑
├── prompts/           # 规划、研究、写作与压缩提示词
├── tools/
│   ├── scraper/       # HTTPX、BS4、Playwright 与 URL 安全
│   └── search/        # Tavily 搜索
├── __init__.py        # 稳定公共 API
└── cli.py             # 命令行入口
```

依赖方向固定为：

```text
models / prompts / config
          ↓
context / tools / observability
          ↓
orchestration
          ↓
agent
          ↓
cli
```

## 核心模块

| 模块 | 主要职责 |
|---|---|
| `agent/planner.py` | 生成结构化研究计划；解析失败重试一次后降级为单任务计划 |
| `agent/researcher.py` | 在当前子任务边界内选择搜索、抓取或显式完成任务 |
| `agent/writer.py` | 只消费计划、章节状态和 ResearchNote，输出最终报告及使用的笔记 ID |
| `agent/service.py` | `ResearchAgent`、`AgentResult`、真实依赖组装和 LangGraph 门面 |
| `orchestration/` | 六节点研究图、串行任务调度、覆盖计算、全局预算和工具结果回填 |
| `context/` | 800/100 分块、BGE-M3 向量注册表、双查询 max 召回、ResearchNote 压缩 |
| `tools/search/` | Tavily 搜索、来源排序、注册域名多样性和候选结果整理 |
| `tools/scraper/` | URL 安全、HTML 发布时间元数据、HTTPX/Trafilatura/BS4/Playwright 抓取降级链 |
| `models/` | 可序列化的计划、任务、覆盖状态、章节、事件、文档、笔记和 Token 模型 |
| `prompts/` | 统一管理 Planner、Researcher、Writer 与压缩提示词 |
| `observability/` | 逐轮上下文基线、毛节省、压缩成本和净节省 |
| `config/` | Settings 和环境变量验证 |

长提示词只放在 `prompts/`。Planner 和 Writer 使用提示词约束 JSON，再由本地修复与 Pydantic 严格校验，以兼容不支持 `response_format` 或工具式结构化输出的 OpenAI-compatible Provider。阶段 4 的 Evidence Store、Verifier 及后续模块尚未实现。

## 核心流程

```text
Planner → Researcher → 搜索/抓取 → 网页分块 → BGE-M3 双查询召回
                    → 并发压缩 ResearchNote → 覆盖判断 → 下一任务
                                                       ↓
                         Writer ← 计划 + 章节状态 + ResearchNote
```

子任务串行执行；每轮最多实际抓取 3 个排序后的候选，同一轮网页抓取和压缩保持有界并发，单次压缩调用有 60 秒硬超时。同一页面遇到新子问题时复用正文、chunks 和内存向量，只重新筛选并生成带 `task_id`、`section_id` 的新笔记。系统按任务轮数、连续空轮、来源覆盖、网页数、步骤、运行时间、Provider Token 和可选费用预算确定性停止。

研究笔记区分页面发布时间与事件发生时间。后发文章可以作为 `retrospective` 回顾目标期；`out_of_range` 不进入覆盖和 Writer，时间未知内容不能支撑充分覆盖。`sufficient` 还要求至少两个注册域名身份，并至少包含一条官方、学术或高质量二手来源，但仍不代表 Claim 级事实验证。最终报告会显式披露部分完成、失败章节和未做 Claim 级验证的限制。

CLI 会输出搜索候选数、抓取成功/失败/跳过数、有效/后发回顾/时间未知/超范围笔记数和失败码，并分别汇总 Planner、Researcher、Compression、Writer 的 Provider Token。任务 Token 额度按剩余任务动态分配，`DEEPTRACE_WRITER_TOKEN_RESERVE_RATIO` 专门保留 Writer 预算；任务额度耗尽只结束当前任务，不会提前跳过后续任务。

## 本地验证

```powershell
uv run pytest -m "not real"
uv run python -m compileall src tests
```

普通测试不调用外部 API。真实端到端验证直接运行 `uv run deeptrace "问题"`，必须使用真实 LLM、Tavily、网页抓取和本地 BGE-M3；`partial` 或 `failed` 状态会返回非零退出码。
