# DeepTrace 阶段 2

DeepTrace 是命令行深度研究 Agent。主模型自主调用搜索与网页抓取工具；整页正文先经过本地 BGE-M3 召回和 LLM 压缩，主 Agent 只读取相关研究笔记。

## 运行

复制 .env.example 为 .env，填写真实 OpenAI 兼容接口和 Tavily Key：

    uv sync
    uv run playwright install chromium
    uv run deeptrace "今天 AI Agent 领域有哪些热点新闻？"

Chromium 只在 HTTPX 无法提取足够正文时启用。

若程序运行在会把公网域名映射到 198.18.0.0/15 的受控代理或沙箱中，可设置
DEEPTRACE_ALLOW_BENCHMARK_DNS_PROXY=true。普通网络环境不要开启；该开关只影响
域名解析结果，URL 直接使用非公网 IP 仍会被拒绝。

## 核心流程

graph.py 定义 agent → tools → agent 的 LangGraph 闭环。nodes.py 负责构造有界上下文、执行搜索、并发抓取、批量向量化、双查询召回和并发压缩。并发结果按原始 tool_call_id 回填，避免页面错配。

同一页面再次用于新子问题时会复用文档、chunks 和内存中的向量，只重新筛选并生成新笔记。软上限为 8 步；存在新证据且查询不重复时可延长一次，硬上限为 12 步。

## 文件功能

- agent.py：ResearchAgent 门面和 build_real_agent 真实依赖组装。
- nodes.py / graph.py：Agent 编排和节点实现。
- fetching.py：HTTPX + Trafilatura/BeautifulSoup，必要时降级 Playwright。
- embedding.py：BGE-M3 分块、向量缓存与双查询 max 召回。
- compression.py：结构化笔记、JSON 修复、重试和抽取式降级。
- token_metrics.py：逐轮估算整页基线、压缩后上下文、毛节省和净节省。
- models.py / state.py：数据模型、Graph State 和 reducer。
- tools.py / urls.py：Tavily 搜索、工具 schema、URL 安全与文档去重。
- cli.py：输出进度、答案、来源和 Token 汇总。

## 本地验证

    uv run pytest -m "not real"
    uv run python -m compileall src

普通测试不会调用外部 API。真实端到端验证直接运行 deeptrace 命令。
