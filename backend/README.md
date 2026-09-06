# ResearchPilot 后端

ResearchPilot 提供 Basic、Deep 与 Multi-Agent 三种平级模式。Basic 参考 GPT-Researcher 的基础报告路径；Deep 使用 Plan-and-Execute、ReAct 原生工具调用与动态重规划；Multi-Agent 使用 LangGraph 编排 Supervisor Plan-and-Execute 和多个独立 ReAct Researcher。Python 包名、旧 CLI 命令和环境变量前缀继续兼容 DeepTrace。

## Multi-Agent 协作研究模式

```text
START → Plan（Supervisor 建立持久任务表）
      → Execute（限并发运行多个隔离的 ReAct Researcher）
      → Replan（按叶子任务缺口补充任务或结束）
      ↘ 有就绪任务时回到 Execute
      → Writer（汇总实际读取并经 BGE 筛选的原文）→ END
```

Multi-Agent 是独立的第三种执行策略，不替换也不调用 Deep 的流程代码。它自己的顶层也是 Plan-and-Execute，但由 LangGraph 状态图持久保存 r1、r2 等任务及父子关系。默认最多创建 6 个研究员任务，单批最多 3 个并同时执行 3 个；Supervisor 最多决策 3 轮。每个 Researcher 总共最多决策 3 轮，前两轮各最多执行一个研究工具，最后一轮只允许结构化收尾。整次运行仍只有 30 次实际网络搜索/抓取额度，首批执行前预留 20% 给定向补查，单个研究员最多使用 10 次。

相同搜索和 URL 在同次运行内采用单飞与缓存复用，只有实际发起网络请求的一方扣额度；失败尝试也计数。模型不直接调用 `search_web`，而是通过一次 `research_topic` 完成导航搜索和少量原文读取。搜索观察最多返回 3 条结果，标题和摘要分别限制为 200、300 字符；Researcher 每个来源最多看到 1,200 字符，Writer 可使用每来源最多 3,000 字符、整次最多 30,000 字符的 BGE 筛选原文。

每个 Researcher 的消息、已知 URL、已读来源和本地额度相互隔离，一个任务失败不会取消同批任务。`researcher.queued` 表示等待并发槽，`researcher.started` 才表示实际开始执行；单轮请求多个工具时只执行第一个并产生 `tool.batch_limited`。Supervisor 无效结构最多修复一次；调用超时不再重试，会打开本次运行的主管熔断并按叶子缺口生成确定性补查。只要仍有叶子缺口和执行容量，任何结束决策都会产生 `plan.finish_rejected`，不会提前写报告。任务已无缺口，或研究员、网络额度、主管轮次已经形成硬边界时，系统直接进入 Writer，不再调用无法改变路由结果的 Supervisor。补查没有新增来源时以 `stagnant` 收尾，避免重复消耗。应用当前日期与时区会明确传入 Supervisor、Researcher 和 Writer。任务摘要只供 Supervisor 协调，Writer 的事实输入仍是网页正文或 BGE 筛选的原文片段，不建立 `ResearchNote`、Claim、Evidence 或 Verifier 对象。

```powershell
uv run researchpilot --mode multi_agent "研究问题"
```

API 请求 mode 使用 `multi_agent`。耗时、Token 与估算费用只作观测，不作为停止条件；停止边界仍是 Supervisor/Researcher 循环数、全局/局部工具调用数和单次调用超时。各角色调用耗时是累计值，并发时相加后可能大于整次运行的墙钟耗时。

## Deep 研究模式

```text
Planner（任务、完成条件、依赖）
  → 按依赖选择任务
  → Executor：模型选工具 → 工具结果 → 再次决策
  → 任务结束/受阻/存在缺口 → Replanner 检查已读原文和执行反馈
  → 替换剩余计划继续执行，或进入 Writer
```

工具包括 `search_web(query)`、`fetch_page(url, refresh=false)`、
`search_memory(query)` 与 `finish_task(status, gaps)`。支持读取用户明确给出的
URL，或搜索/记忆返回的 URL；请求仍经过现有抓取器的地址校验。
每轮最多三个独立读工具并行，任务本身按依赖顺序执行。

默认上限：6 个已执行任务、每任务 4 轮、全局 12 轮 Executor、2 次重规划、
30 次研究工具调用。使用 `DEEPTRACE_DEEP_*` 调整（见 `.env.example`）。
搜索、阅读和记忆检索共用工具配额，包括缓存命中及失败调用；并行调用不会超额。
`submit_plan` 和 `finish_task` 属于控制决策，由规划/执行轮次限制，不扣研究工具配额。
不设总时长、累计 Token 或费用预算，达到次数上限后仍正常生成报告。
单次请求保留故障超时；耗时和 Provider 已返回的 Token 按角色统计，超时未返回的用量无法准确统计。

`DEEPTRACE_USE_MEMORY=true` 启用跨运行语义资料检索。Deep 默认只检索 7 天内
抓取的页面，在最近 100 页中用 BGE 排序，取相似度至少 0.42 的前三页。
`fetch_page(refresh=true)` 可绕过历史缓存核验最新事实。工作记忆始终可用。

```powershell
uv run researchpilot --mode deep "研究问题"
```

API 请求 `POST /researches` 的 JSON 可使用 `{"question":"研究问题","mode":"deep"}` 或 `mode: "multi_agent"`；
省略 mode 时仍使用 Basic。事件保留任务计划、工具结果状态、重规划及最终统计。
失败或次数上限终止可返回 partial 报告，不代表研究目标全部完成。

## Basic 流程

```text
用户问题
  → 首次搜索
  → Planner 生成 3 个扁平搜索词，并追加原问题去重
  → 所有搜索词并行搜索
  → URL 全局去重，最多 15 路并发抓取
  → 小文本直接使用，大文本由本地 BGE-M3 筛选相关原文
  → 拼成 Source / Title / Content 文本
  → Writer 一次生成报告
```

运行图固定为 `START → plan → parallel_research → writer → END`。系统不建立任务树，不执行多轮研究循环，也不保存中间证据实体。搜索、抓取和本地向量筛选不调用 LLM，Provider Token 只统计 Planner 和 Writer。

## 输入 Writer 的内容

每段资料使用以下格式：

```text
Source: https://example.com/article
Title: 页面标题
Content: 网页正文或 BGE-M3 筛选出的相关原文
```

`Content` 是源网页文本，不是 LLM 摘要。总正文小于 8000 字符且来源数不超过上限时直接传入；较大内容按 1000 字符切分、重叠 100 字符，以 0.42 相似度阈值筛选，每个搜索词最多保留 10 段。Writer 在正文中使用按首次出现顺序生成的 `[1]` 编号引用，正文不显示 URL，文末统一列入“参考内容”。中文报告依次包含总述、带自然承接的主题分析、存在实质缺口时的研究局限和正文最后的综合结论；仍只调用一次 Writer。报告标题使用 `1`、`1.1`、`1.1.1` 数字层级，不使用 `#`。最后一条研究事件汇总本次运行总耗时与 Planner、Writer 的 Provider Token 用量。

## 运行

复制 `.env.example` 为 `.env`，填写 OpenAI-compatible Provider 和 Tavily 凭据：

```powershell
uv sync
uv run playwright install chromium
uv run deeptrace "今天 AI Agent 领域有哪些热点新闻？"
```

启动 Web 界面：

```powershell
uv run python -m deeptrace.api
```

浏览器访问 `http://127.0.0.1:8000/`。API 提供：

- `POST /researches` 创建后台研究运行
- `GET /researches/{id}` 获取状态、搜索词、报告、来源与用量
- `GET /researches/{id}/events` 订阅 SSE 进度事件
- `POST /researches/{id}/cancel` 取消运行

运行记录保存到 `runs/<id>.json`。开启 `DEEPTRACE_USE_MEMORY=true` 后，成功抓取的完整页面可跨运行复用；缓存命中不占网络抓取页数。

## 主要配置

```text
DEEPTRACE_SEARCH_QUERY_COUNT=3
DEEPTRACE_MAX_SEARCH_RESULTS_PER_QUERY=5
DEEPTRACE_SCRAPER_CONCURRENCY=15
DEEPTRACE_CONTEXT_MAX_RESULTS=10
DEEPTRACE_CONTEXT_DIRECT_THRESHOLD_CHARS=8000
DEEPTRACE_CONTEXT_CHUNK_CHARS=1000
DEEPTRACE_CONTEXT_CHUNK_OVERLAP_CHARS=100
DEEPTRACE_CONTEXT_SIMILARITY_THRESHOLD=0.42
DEEPTRACE_PLANNER_TIMEOUT_SECONDS=60
DEEPTRACE_WRITER_TIMEOUT_SECONDS=60
DEEPTRACE_MAX_FETCHED_PAGES=20
DEEPTRACE_MAX_TOOL_CALLS=30
DEEPTRACE_TOOL_TIMEOUT_SECONDS=45
```

`DEEPTRACE_EMBEDDING_MODEL_PATH` 指向本地 BGE-M3 目录。`DEEPTRACE_INPUT_COST_PER_MILLION` 和 `DEEPTRACE_OUTPUT_COST_PER_MILLION` 只用于费用估算。

旧的 `DEEPTRACE_MAX_RUNTIME_SECONDS`、`DEEPTRACE_MAX_COST_USD`、`DEEPTRACE_DEEP_MAX_TOKENS` 已不再生效，不必为了取消预算修改现有 `.env`。`OPENAI_MAX_TOKENS` 仍控制模型单次最大输出长度，与累计预算无关。
Basic 搜索与网络抓取共用 30 次工具配额，并保留最多 20 次网络抓取的子上限；复用缓存不发起网络调用。

## 代码结构

```text
src/deeptrace/
├── basic/             # Basic：LangGraph 一轮研究管线
├── deep/              # Deep：Plan-and-Execute、ReAct 与动态重规划
├── multi_agent/       # LangGraph Supervisor Plan/Execute/Replan 与多 Researcher
├── writer/            # 三种模式共用的 Writer 与报告渲染
├── config/            # 环境配置与校验
├── context/           # BGE-M3 与直接原文筛选
├── models/            # 页面、事件和 Provider 用量模型
├── observability/     # 费用估算与各角色用量展示
├── prompts/           # Planner 与 Writer 提示词
├── tools/             # Tavily 搜索与网页抓取
├── memory.py          # 页面级 JSONL 缓存
├── api.py             # FastAPI、SSE 和 Web 仪表盘
└── cli.py             # 命令行入口
```

## 验证

```powershell
uv lock --check
uv run pytest -m "not real"
uv run python -m compileall -q src tests
uv run deeptrace --help
```

普通测试不调用外部 API。真实冒烟可运行 `uv run python bench_run.py`（Basic）或 `uv run python bench_deep.py --output runs/deep-smoke.json`（Deep）。Multi-Agent 可通过 Web 或 CLI 的 `multi_agent` 模式验证。不设总运行时间或 Token 预算，真实调用会产生 Provider 费用。
