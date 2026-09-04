# DeepTrace

DeepTrace 当前实现的是单一的 Basic 研究模式。流程参考 GPT-Researcher 的基础报告路径，目标是先把稳定、快速的端到端能力跑通，再在此基础上做优化。

## 当前流程

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

`Content` 是源网页文本，不是 LLM 摘要。总正文小于 8000 字符且来源数不超过上限时直接传入；较大内容按 1000 字符切分、重叠 100 字符，以 0.42 相似度阈值筛选，每个搜索词最多保留 10 段。Writer 负责在正文中使用 Markdown 链接，系统在末尾补充稳定去重的 References 列表。

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
DEEPTRACE_MAX_RUNTIME_SECONDS=300
```

`DEEPTRACE_EMBEDDING_MODEL_PATH` 指向本地 BGE-M3 目录。`DEEPTRACE_INPUT_COST_PER_MILLION` 和 `DEEPTRACE_OUTPUT_COST_PER_MILLION` 可用于费用估算；设置 `DEEPTRACE_MAX_COST_USD` 时必须同时提供两项单价。

## 代码结构

```text
src/deeptrace/
├── agent/             # Planner、Writer 和公共 ResearchAgent
├── config/            # 环境配置与校验
├── context/           # BGE-M3 与直接原文筛选
├── models/            # 页面、事件和 Provider 用量模型
├── observability/     # 费用估算与两角色用量展示
├── orchestration/     # 三节点图、全局预算和并行采集
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

普通测试不调用外部 API。真实回归可以运行 `uv run python bench_run.py`，默认总运行时上限为 300 秒。
