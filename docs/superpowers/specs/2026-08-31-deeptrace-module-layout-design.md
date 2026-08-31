# DeepTrace 模块化目录重构设计

- 状态：已确认，待实施
- 日期：2026-08-31
- 实施范围：`backend/src/deeptrace/`、对应测试和 `backend/README.md`
- 目标：将阶段 2 代码按业务能力拆入子包，为后续 Agent、Evidence、Memory 与评测模块提供清晰边界

## 1. 设计原则

本次只重构目录、模块职责和导入关系，不修改阶段 2 的算法与运行行为。LangGraph 编排、BGE-M3 双查询召回、ResearchNote 压缩、抓取降级链、Token 统计及 CLI 行为均保持不变。

- 按业务能力组织代码，不按技术层堆放大文件。
- 每个模块只承担一种主要职责，并通过明确接口协作。
- 底层模块不得反向依赖编排层和 Agent 层。
- 不提前创建尚未实现的 `memory/`、`evidence/`、`evaluation/` 空目录。
- 提示词集中在 `prompts/` 管理，业务函数中不保留长提示词字符串。
- 只保留 `deeptrace` 包根部的稳定公共 API，不维护旧内部导入路径的兼容转发文件。

## 2. 目标目录

```text
backend/src/deeptrace/
├── __init__.py
├── cli.py
├── agent/
│   ├── __init__.py
│   └── service.py
├── orchestration/
│   ├── __init__.py
│   ├── graph.py
│   ├── nodes.py
│   └── state.py
├── context/
│   ├── __init__.py
│   ├── chunking.py
│   ├── embeddings.py
│   ├── retrieval.py
│   └── compression.py
├── tools/
│   ├── __init__.py
│   ├── search/
│   │   ├── __init__.py
│   │   └── tavily.py
│   └── scraper/
│       ├── __init__.py
│       ├── fetcher.py
│       └── urls.py
├── models/
│   ├── __init__.py
│   ├── document.py
│   ├── research.py
│   └── metrics.py
├── prompts/
│   ├── __init__.py
│   ├── research.py
│   └── compression.py
├── observability/
│   ├── __init__.py
│   └── token_metrics.py
└── config/
    ├── __init__.py
    └── settings.py
```

## 3. 模块职责

### agent

`agent/service.py` 提供 `ResearchAgent`、`AgentResult` 和 `build_real_agent`，负责组装真实依赖并向 CLI 或未来 API 暴露统一运行入口。它不实现具体抓取、召回或压缩算法。

### orchestration

`graph.py` 构建 LangGraph 并定义节点路由；`nodes.py` 实现阶段 2 的工作流节点；`state.py` 定义 `GraphState` 和 reducer。该包只负责流程协调，通过接口调用 context、tools 与 observability。

### context

`chunking.py` 负责网页分块；`embeddings.py` 负责 BGE-M3 加载、批量向量化和进程内向量注册表；`retrieval.py` 负责双查询 max 融合、相邻块扩展、ResearchNote 召回和重复查询检测；`compression.py` 负责 LLM 结构化压缩、JSON 修复、重试与抽取式降级。

### tools

`tools/__init__.py` 暴露工具 Schema、工具上下文和注册接口。`search/tavily.py` 封装 Tavily 搜索。`scraper/fetcher.py` 实现 HTTPX、BeautifulSoup、Playwright 降级链及并发控制；`scraper/urls.py` 负责 URL 校验与规范化。

### models

`document.py` 定义 `RawDocument`、`DocumentChunk` 和抓取相关枚举；`research.py` 定义 `ResearchNote`、`CompressionOutcome` 等研究对象；`metrics.py` 定义 Token usage 与统计结果。models 不依赖 LangGraph、LLM Provider、Tavily 或抓取实现。

### prompts

`research.py` 集中管理主 Agent 研究、继续搜索和最终回答提示词；`compression.py` 集中管理网页压缩提示词。提示词模块只保存模板和纯构造函数，不调用模型、不读取 GraphState，也不包含运行时副作用。阶段 3 以后按能力增加 `planner.py`、`researcher.py`、`writer.py`，而不是继续扩大单个文件。

### observability 与 config

`observability/token_metrics.py` 负责 Token 估算、账本、公式和 CLI 格式化。`config/settings.py` 负责环境变量读取、默认值和配置校验。

## 4. 依赖方向

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

同层模块可以通过公共接口协作，但不得形成循环导入。项目内部使用 `from deeptrace.<package>...` 形式的绝对导入。各子包的 `__init__.py` 只显式导出稳定接口，不使用通配符导入。

## 5. 文件迁移

| 当前文件 | 目标位置 |
|---|---|
| `agent.py` | `agent/service.py` |
| `graph.py` | `orchestration/graph.py` |
| `nodes.py` | `orchestration/nodes.py` |
| `state.py` | `orchestration/state.py` |
| `embedding.py` | `context/chunking.py`、`context/embeddings.py`、`context/retrieval.py` |
| `compression.py` | `context/compression.py` |
| `tools.py` | `tools/__init__.py`、`tools/search/tavily.py` |
| `fetching.py` | `tools/scraper/fetcher.py` |
| `urls.py` | `tools/scraper/urls.py` |
| `models.py` | `models/document.py`、`models/research.py`、`models/metrics.py` |
| `token_metrics.py` | `observability/token_metrics.py` |
| `config.py` | `config/settings.py` |
| 分散在业务文件中的提示词 | `prompts/research.py`、`prompts/compression.py` |
| `cli.py` | 保留位置并更新导入 |

## 6. 公共接口

包根部继续支持：

```python
from deeptrace import AgentResult, ResearchAgent, build_real_agent
```

`deeptrace.embedding`、`deeptrace.fetching`、`deeptrace.models` 文件形式的旧内部路径不承诺兼容。仓库内代码和测试一次性迁移到新路径，避免新旧结构长期并存。

## 7. 测试与验收

测试按目标子包调整导入和目录，但不增加大规模评测。重构验收条件如下：

1. 现有非真实测试全部通过。
2. 现有真实端到端研究闭环通过一次。
3. `uv run deeptrace "问题"` 的参数、输出和错误处理保持不变。
4. `deeptrace` 包根部三个公共入口保持可导入。
5. 源码中不存在对已移除顶层内部模块的导入。
6. 长提示词只存在于 `prompts/`。
7. README 包含最新目录树、文件职责和依赖方向。

## 8. 后续扩展

阶段 3 实现时再新增多 Agent 相关目录；阶段 4 至 5 新增 `evidence/`；阶段 6 新增 `memory/`；阶段 9 新增 `evaluation/`。新增目录必须伴随可运行实现，不建立空壳。
