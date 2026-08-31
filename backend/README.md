# DeepTrace 阶段 2

DeepTrace 是命令行深度研究 Agent。主模型自主调用搜索和网页抓取工具；整页正文先经过本地 BGE-M3 召回与 LLM 压缩，主 Agent 只读取相关 ResearchNote。

## 运行

复制 `.env.example` 为 `.env`，填写真实 OpenAI-compatible 接口和 Tavily Key：

```powershell
uv sync
uv run playwright install chromium
uv run deeptrace "今天 AI Agent 领域有哪些热点新闻？"
```

Chromium 只在 HTTPX 无法提取足够正文时启用。受控代理或沙箱把公网域名映射到 `198.18.0.0/15` 时，可以显式设置 `DEEPTRACE_ALLOW_BENCHMARK_DNS_PROXY=true`；普通网络环境不要开启。

## 目录结构

```text
src/deeptrace/
├── agent/             # Agent 门面与真实依赖组装
├── config/            # 环境变量、默认值和配置校验
├── context/           # 分块、BGE-M3、召回与压缩
├── models/            # 文档、研究笔记与指标模型
├── observability/     # Token 估算、账本和格式化
├── orchestration/     # LangGraph State、节点与拓扑
├── prompts/           # 研究与压缩提示词
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
| `agent/service.py` | `ResearchAgent`、`AgentResult` 和 `build_real_agent` |
| `orchestration/` | LangGraph 状态、节点、工具回填和路由 |
| `context/` | 800/100 分块、BGE-M3 向量注册表、双查询 max 召回、ResearchNote 压缩 |
| `tools/search/` | Tavily 搜索和候选结果整理 |
| `tools/scraper/` | URL 安全、HTTPX/Trafilatura/BS4/Playwright 抓取降级链 |
| `models/` | 可序列化的文档、笔记和 Token 数据模型 |
| `prompts/` | 统一管理主 Agent 与压缩提示词 |
| `observability/` | 逐轮上下文基线、毛节省、压缩成本和净节省 |
| `config/` | Settings 和环境变量验证 |

长提示词只放在 `prompts/`。阶段 3 的 Planner、Researcher、Writer 以及后续 Evidence、Memory、Evaluation 模块，在真正实现时再建立目录，不创建空壳。

## 核心流程

```text
Agent → 搜索/抓取 → 网页分块 → BGE-M3 双查询召回
      → 并发压缩 ResearchNote → 按 tool_call_id 回填 → Agent
```

同一页面遇到新子问题时复用正文、chunks 和内存向量，只重新筛选并生成新笔记。软上限为 8 步；存在新证据且查询不重复时可延长一次，硬上限为 12 步。

## 本地验证

```powershell
uv run pytest -m "not real"
uv run python -m compileall src
```

普通测试不调用外部 API。真实端到端验证直接运行 `uv run deeptrace "问题"`。
