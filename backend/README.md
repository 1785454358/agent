# DeepTrace 阶段 4

DeepTrace 是命令行规划式深度研究 Agent。Planner 拆分问题，Researcher 使用真实搜索和网页抓取形成 ResearchNote；Evidence Store 将笔记回溯为 Source 与原文 Evidence，Claim Extractor 生成原子 Claim，Verifier 完成规则与 LLM 联合判断，并可触发一次有界补搜。Writer 只把验证通过的 Claim 写成确定事实。

## 运行

复制 `.env.example` 为 `.env`，填写真实 OpenAI-compatible 接口和 Tavily Key：

```powershell
uv sync
uv run playwright install chromium
uv run deeptrace "今天 AI Agent 领域有哪些热点新闻？"
```

Chromium 只在 HTTPX 无法提取足够正文时启用。受控代理或沙箱把公网域名映射到 `198.18.0.0/15` 时，可以显式设置 `DEEPTRACE_ALLOW_BENCHMARK_DNS_PROXY=true`；普通网络环境不要开启。

阶段 4 的主要预算环境变量及默认值如下：

```text
DEEPTRACE_MAX_RESEARCH_TASKS=4
DEEPTRACE_MAX_TASK_ROUNDS=3
DEEPTRACE_MIN_SOURCES_PER_TASK=2
DEEPTRACE_MAX_FETCHED_PAGES=20
DEEPTRACE_MAX_RUNTIME_SECONDS=600
DEEPTRACE_MAX_API_TOKENS=120000
DEEPTRACE_RESEARCH_RUNTIME_RATIO=0.70
DEEPTRACE_VERIFICATION_RESERVE_RATIO=0.20
DEEPTRACE_WRITER_TOKEN_RESERVE_RATIO=0.15
DEEPTRACE_MAX_VERIFICATION_GAPS_PER_TASK=2
DEEPTRACE_MAX_VERIFICATION_FETCHES_PER_TASK=3
DEEPTRACE_MAX_VERIFICATION_ROUNDS_PER_TASK=1
```

可选的 `DEEPTRACE_INPUT_COST_PER_MILLION`、`DEEPTRACE_OUTPUT_COST_PER_MILLION` 和 `DEEPTRACE_MAX_COST_USD` 用于费用估算及上限；设置费用上限时必须同时提供输入、输出单价。

## 目录结构

```text
src/deeptrace/
├── agent/             # Planner、Researcher、Claim Extractor、Verifier、Writer 与门面
├── config/            # 环境变量、默认值和配置校验
├── context/           # 分块、BGE-M3、召回与压缩
├── evidence/          # 运行内 Source、Evidence、Claim 入库与稳定 ID
├── verification/      # 确定性规则、LLM 验证与缺口规划
├── models/            # 计划、研究、证据、验证与指标模型
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
| `agent/claim_extractor.py` | 从已定位 Evidence 抽取原子 Claim；两次限时调用失败后确定性降级 |
| `agent/verifier.py` | 将规则结果与 LLM 支持、反驳、无关判断合并，失败时不升级为 verified |
| `agent/writer.py` | 只消费计划、验证摘要和可用 Claim，输出 Claim 级引用 |
| `agent/service.py` | `ResearchAgent`、`AgentResult`、真实依赖组装和 LangGraph 门面 |
| `orchestration/` | 逐任务研究、证据入库、抽取、验证、一次补搜、写作和全局预算 |
| `evidence/` | Source → Evidence → Claim 的运行内可追溯链与字符定位 |
| `verification/` | 时间、数字、来源规则，判定合并和结构化补搜 Gap |
| `context/` | 800/100 分块、BGE-M3 向量注册表、双查询 max 召回、ResearchNote 压缩 |
| `tools/search/` | Tavily 搜索、来源排序、注册域名多样性和候选结果整理 |
| `tools/scraper/` | URL 安全、HTML 发布时间元数据、HTTPX/Trafilatura/BS4/Playwright 抓取降级链 |
| `models/` | 可序列化的计划、研究、Source、Evidence、Claim、验证、事件和 Token 模型 |
| `prompts/` | 统一管理 Planner、Researcher、Writer 与压缩提示词 |
| `observability/` | 逐轮上下文基线、毛节省、压缩成本和净节省 |
| `config/` | Settings 和环境变量验证 |

长提示词只放在 `prompts/`。模型 JSON 经过本地修复与 Pydantic 严格校验，以兼容不支持工具式结构化输出的 OpenAI-compatible Provider。Evidence Store 仅存在于单次运行内；Memory、数据库、API、Web UI 和规模化评测尚未实现。

## 核心流程

```text
Planner → Researcher → 搜索/抓取 → BGE-M3 召回 → ResearchNote
                    → Evidence Store → Claim Extractor → Verifier
                                      ↘ 关键缺口 → 一次有界补搜 ↗
                                                       ↓
                         Writer ← verified Claim + Source
```

子任务串行执行；每轮最多实际抓取 3 个排序后的候选，同一轮网页抓取和压缩保持有界并发，单次压缩调用有 60 秒硬超时。同一页面遇到新子问题时复用正文、chunks 和内存向量，只重新筛选并生成带 `task_id`、`section_id` 的新笔记。系统按任务轮数、连续空轮、来源覆盖、网页数、步骤、运行时间、Provider Token 和可选费用预算确定性停止。

研究笔记区分页面发布时间与事件发生时间，后发回顾文章可支持目标期事实。只有能在真实 RawDocument 中精确字符定位的 Evidence 才能支撑 Claim；`unlocated` 仅保留诊断。Writer 对 `verified` Claim 使用确定语气，对其他状态只作缺口或局限披露，并从实际使用 Claim 反向生成来源列表。

CLI 会额外输出 Source、Evidence、精确定位、Claim、各验证状态、Gap、补搜及报告实际使用 Claim/来源数量，并分别汇总 Planner、Researcher、Compression、Claim Extractor、Verifier、Writer 的 Provider Token。普通研究只使用运行时间的前 70%，验证预留 20%，其余留给最终写作和收尾。

## 本地验证

```powershell
uv run pytest -m "not real"
uv run python -m compileall src tests
```

普通测试不调用外部 API。真实端到端验证直接运行 `uv run deeptrace "问题"`，必须使用真实 LLM、Tavily、网页抓取和本地 BGE-M3；`partial` 或 `failed` 状态会返回非零退出码。
