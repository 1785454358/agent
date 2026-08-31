# DeepTrace 模块化目录重构实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将阶段 2 的顶层 Python 文件迁移为按业务能力组织的子包，同时保持 CLI、LangGraph、抓取、压缩和 Token 统计行为不变。

**Architecture:** 迁移按依赖方向从底向上进行。`models`、`prompts` 和 `config` 作为基础层；`context`、`tools` 和 `observability` 提供能力；`orchestration` 组合工作流；`agent` 与 `cli` 作为入口。迁移期间允许旧文件短暂存在，每个任务结束时必须有可运行的新接口，最终删除全部旧内部模块。

**Tech Stack:** Python 3.11、Pydantic、LangChain Core、LangGraph、SentenceTransformers/BGE-M3、Tavily、HTTPX、Trafilatura、BeautifulSoup、Playwright、tiktoken、pytest。

**Spec:** `docs/superpowers/specs/2026-08-31-deeptrace-module-layout-design.md`

## Global Constraints

- 本次只调整目录、职责、提示词位置和导入，不修改阶段 2 算法、阈值、默认值、CLI 参数或输出语义。
- 包根部继续导出 `AgentResult`、`ResearchAgent`、`build_real_agent`。
- 项目内部统一使用 `from deeptrace.<package>...` 绝对导入。
- 子包 `__init__.py` 只显式导出稳定接口，不使用通配符导入。
- `models` 不依赖 LangGraph、模型服务、Tavily、抓取器或 Agent。
- 长提示词只能位于 `deeptrace/prompts/`。
- 不创建 `memory`、`evidence`、`evaluation` 等没有实现的空目录。
- 只运行现有回归测试、模块导入契约测试和一次真实 CLI 冒烟，不开展大规模评测。
- 每次提交只暂存本任务文件，不包含工作区内既有的无关修改。

---

### Task 1: 建立 models、config 与 prompts 基础包

**Files:**
- Create: `backend/src/deeptrace/models/__init__.py`
- Create: `backend/src/deeptrace/models/document.py`
- Create: `backend/src/deeptrace/models/research.py`
- Create: `backend/src/deeptrace/models/metrics.py`
- Create: `backend/src/deeptrace/config/__init__.py`
- Create: `backend/src/deeptrace/config/settings.py`
- Create: `backend/src/deeptrace/prompts/__init__.py`
- Create: `backend/src/deeptrace/prompts/research.py`
- Create: `backend/src/deeptrace/prompts/compression.py`
- Modify: `backend/src/deeptrace/nodes.py`
- Modify: `backend/src/deeptrace/compression.py`
- Delete: `backend/src/deeptrace/models.py`
- Delete: `backend/src/deeptrace/config.py`
- Create: `backend/tests/test_module_layout.py`
- Move: `backend/tests/test_config.py` → `backend/tests/config/test_settings.py`
- Modify: `backend/tests/test_graph.py`

**Interfaces:**
- Produces: `deeptrace.models` 显式导出的 `PendingFetch`、`ScraperUsed`、`RawDocument`、`DocumentChunk`、`ResearchNote`、`TokenUsage`、`ContextAudit`、`PageCompressionMetrics`、`RoundTokenMetrics`、`CompressionOutcome`。
- Produces: `deeptrace.config.Settings`。
- Produces: `build_system_prompt(today: date | None = None) -> str` 和 `FINAL_REPORT_PROMPT`。
- Produces: `build_compression_messages(*, active_query: str, title: str, url: str, chunks: Sequence[tuple[int, str]]) -> list[BaseMessage]`。

- [ ] **Step 1: 写新包导入与提示词归属测试**

在 `backend/tests/test_module_layout.py` 写入：

```python
from datetime import date

from deeptrace.config import Settings
from deeptrace.models import RawDocument, ResearchNote, TokenUsage
from deeptrace.prompts.compression import build_compression_messages
from deeptrace.prompts.research import FINAL_REPORT_PROMPT, build_system_prompt


def test_foundation_packages_expose_stable_interfaces() -> None:
    assert Settings.__name__ == "Settings"
    assert RawDocument.__name__ == "RawDocument"
    assert ResearchNote.__name__ == "ResearchNote"
    assert TokenUsage.__name__ == "TokenUsage"


def test_prompts_are_built_in_prompts_package() -> None:
    system = build_system_prompt(date(2026, 8, 31))
    messages = build_compression_messages(
        active_query="Agent 岗位要求",
        title="招聘页面",
        url="https://example.com/job",
        chunks=[(0, "要求熟悉 LangGraph")],
    )
    assert "2026-08-31" in system
    assert "停止调用工具" in FINAL_REPORT_PROMPT
    assert "Agent 岗位要求" in str(messages[1].content)
```

- [ ] **Step 2: 运行测试并确认新包尚不存在**

Run: `cd backend && uv run pytest tests/test_module_layout.py -v`

Expected: FAIL，提示 `deeptrace.prompts` 不存在。

- [ ] **Step 3: 拆分数据模型并建立集中导出**

将模型按以下边界原样迁移：

```python
# models/document.py
class PendingFetch(BaseModel): ...
class ScraperUsed(StrEnum): ...
class RawDocument(BaseModel): ...
class DocumentChunk(BaseModel): ...

# models/metrics.py
class TokenUsage(BaseModel): ...
class ContextAudit(BaseModel): ...
class PageCompressionMetrics(BaseModel): ...
class RoundTokenMetrics(BaseModel): ...

# models/research.py
from deeptrace.models.metrics import TokenUsage
class ResearchNote(BaseModel): ...
class CompressionOutcome(BaseModel): ...
```

`models/__init__.py` 用显式 import 和 `__all__` 导出上述类型。字段、校验范围、Literal 和默认工厂逐项复制，不改变序列化结构。完成后删除 `models.py`。

- [ ] **Step 4: 迁移 Settings**

把现有 `config.py` 内容迁入 `config/settings.py`，在 `config/__init__.py` 中仅导出：

```python
from deeptrace.config.settings import Settings

__all__ = ["Settings"]
```

完成后删除 `config.py`，把配置测试移动到 `tests/config/test_settings.py`，测试内容不改变。

- [ ] **Step 5: 提取研究和压缩提示词**

把 `nodes.py` 的 `build_system_prompt`、`FINAL_REPORT_PROMPT` 移到 `prompts/research.py`。把 `CompressionService._messages` 的提示词构造移到 `prompts/compression.py`：

```python
def build_compression_messages(
    *, active_query: str, title: str, url: str,
    chunks: Sequence[tuple[int, str]],
) -> list[BaseMessage]:
    excerpts = "\n\n".join(
        f"[片段 {index}]\n{text}" for index, text in chunks
    )
    return [
        SystemMessage(content=COMPRESSION_SYSTEM_PROMPT),
        HumanMessage(content=(
            f"当前子问题：{active_query}\n页面标题：{title}\n"
            f"页面 URL：{url}\n\n{excerpts}"
        )),
    ]
```

`nodes.py` 改为从 `deeptrace.prompts.research` 导入；`compression.py` 的 `_messages` 调用该纯函数。`test_graph.py` 改从 `deeptrace.prompts.research` 导入 `build_system_prompt`。

- [ ] **Step 6: 运行基础层测试**

Run: `cd backend && uv run pytest tests/test_module_layout.py tests/config/test_settings.py tests/test_state.py tests/test_compression.py tests/test_graph.py -v`

Expected: PASS。

- [ ] **Step 7: 提交基础层迁移**

```bash
git add backend/src/deeptrace/models backend/src/deeptrace/config backend/src/deeptrace/prompts backend/src/deeptrace/models.py backend/src/deeptrace/config.py backend/src/deeptrace/nodes.py backend/src/deeptrace/compression.py backend/tests/test_module_layout.py backend/tests/config/test_settings.py backend/tests/test_config.py backend/tests/test_graph.py
git commit -m "refactor: organize models config and prompts"
```

### Task 2: 建立 tools、search 与 scraper 子包

**Files:**
- Create: `backend/src/deeptrace/tools/__init__.py`
- Create: `backend/src/deeptrace/tools/search/__init__.py`
- Create: `backend/src/deeptrace/tools/search/tavily.py`
- Create: `backend/src/deeptrace/tools/scraper/__init__.py`
- Create: `backend/src/deeptrace/tools/scraper/fetcher.py`
- Create: `backend/src/deeptrace/tools/scraper/urls.py`
- Modify: `backend/src/deeptrace/agent.py`
- Modify: `backend/src/deeptrace/nodes.py`
- Delete: `backend/src/deeptrace/tools.py`
- Delete: `backend/src/deeptrace/fetching.py`
- Delete: `backend/src/deeptrace/urls.py`
- Move: `backend/tests/test_fetching.py` → `backend/tests/tools/scraper/test_fetcher.py`
- Move: `backend/tests/test_urls.py` → `backend/tests/tools/scraper/test_urls.py`
- Modify: `backend/tests/test_module_layout.py`

**Interfaces:**
- Produces: `deeptrace.tools.TOOL_SCHEMAS` 和 `deeptrace.tools.ToolContext`。
- Produces: `search_web(context: ToolContext, query: str, max_results: int = 5) -> dict[str, Any]`。
- Produces: `AsyncWebFetcher`、`WebFetchError`、`ExtractionCandidate`、`is_usable_text`、`is_allowed_dns_resolution`、`select_best_extraction`。
- Produces: `normalize_url_before_fetch`、`validate_public_url`、`resolve_document_identity`。

- [ ] **Step 1: 扩展模块导入测试**

在 `test_module_layout.py` 增加：

```python
from deeptrace.tools import TOOL_SCHEMAS, ToolContext
from deeptrace.tools.scraper import AsyncWebFetcher, normalize_url_before_fetch
from deeptrace.tools.search import search_web


def test_tools_package_exposes_search_and_scraper_interfaces() -> None:
    assert {item["function"]["name"] for item in TOOL_SCHEMAS} == {
        "search_web", "fetch_webpage"
    }
    assert ToolContext.__name__ == "ToolContext"
    assert AsyncWebFetcher.__name__ == "AsyncWebFetcher"
    assert search_web.__name__ == "search_web"
    assert normalize_url_before_fetch("https://example.com/") == "https://example.com"
```

- [ ] **Step 2: 运行新增导入测试并确认失败**

Run: `cd backend && uv run pytest tests/test_module_layout.py -v`

Expected: FAIL，提示 `deeptrace.tools.scraper` 或 `deeptrace.tools.search` 不存在。

- [ ] **Step 3: 迁移搜索工具与注册表**

`tools/search/tavily.py` 接收 `TavilyClient` 依赖并保留现有 `_tool_error` 与 `search_web` 行为。`tools/search/__init__.py` 导出 `ToolContext` 和 `search_web`。工具 JSON Schema 保存在 `tools/__init__.py`，并从 search 子包重新导出 `ToolContext`、`search_web`。

- [ ] **Step 4: 迁移 URL 与抓取器**

把 `urls.py` 原样迁入 `tools/scraper/urls.py`，把 `fetching.py` 原样迁入 `tools/scraper/fetcher.py`。`fetcher.py` 改为：

```python
from deeptrace.models import RawDocument, ScraperUsed
from deeptrace.tools.scraper.urls import (
    normalize_url_before_fetch,
    resolve_document_identity,
    validate_public_url,
)
```

`tools/scraper/__init__.py` 显式导出测试和编排层使用的抓取、质量判断与 URL 接口。随后更新 `agent.py`、`nodes.py` 的导入并删除三个旧顶层文件。

- [ ] **Step 5: 移动工具测试并更新导入**

`test_fetcher.py` 从 `deeptrace.tools.scraper` 导入抓取接口；`test_urls.py` 从 `deeptrace.tools.scraper.urls` 导入 URL 函数。断言内容保持不变。

- [ ] **Step 6: 运行工具层回归测试**

Run: `cd backend && uv run pytest tests/test_module_layout.py tests/tools/scraper -v`

Expected: PASS。

- [ ] **Step 7: 提交工具层迁移**

```bash
git add backend/src/deeptrace/tools backend/src/deeptrace/tools.py backend/src/deeptrace/fetching.py backend/src/deeptrace/urls.py backend/src/deeptrace/agent.py backend/src/deeptrace/nodes.py backend/tests/test_module_layout.py backend/tests/tools backend/tests/test_fetching.py backend/tests/test_urls.py
git commit -m "refactor: organize search and scraper tools"
```

### Task 3: 拆分 context 上下文处理包

**Files:**
- Create: `backend/src/deeptrace/context/__init__.py`
- Create: `backend/src/deeptrace/context/chunking.py`
- Create: `backend/src/deeptrace/context/embeddings.py`
- Create: `backend/src/deeptrace/context/retrieval.py`
- Create: `backend/src/deeptrace/context/compression.py`
- Modify: `backend/src/deeptrace/agent.py`
- Modify: `backend/src/deeptrace/nodes.py`
- Delete: `backend/src/deeptrace/embedding.py`
- Delete: `backend/src/deeptrace/compression.py`
- Move: `backend/tests/test_embedding.py` → `backend/tests/context/test_retrieval.py`
- Move: `backend/tests/test_compression.py` → `backend/tests/context/test_compression.py`
- Modify: `backend/tests/test_module_layout.py`

**Interfaces:**
- Produces: `CompressionRuntime`。
- Produces: `chunk_document(runtime, document, chunk_tokens=800, overlap_tokens=100) -> list[DocumentChunk]`。
- Produces: `ChunkSelection`、`select_relevant_chunks(...) -> ChunkSelection`、`is_repeated_query(...) -> bool`。
- Produces: `note_embedding_text(note: ResearchNote) -> str` 和 `retrieve_notes(...) -> list[ResearchNote]`。
- Produces: `ResearchNotePayload`、`CompressionRequest`、`parse_note_json`、`build_extractive_note`、`CompressionService`。

- [ ] **Step 1: 写 context 导入契约**

在 `test_module_layout.py` 增加：

```python
from deeptrace.context import (
    CompressionRuntime,
    CompressionService,
    chunk_document,
    retrieve_notes,
    select_relevant_chunks,
)


def test_context_package_exposes_compression_pipeline() -> None:
    assert CompressionRuntime.__name__ == "CompressionRuntime"
    assert CompressionService.__name__ == "CompressionService"
    assert chunk_document.__name__ == "chunk_document"
    assert retrieve_notes.__name__ == "retrieve_notes"
    assert select_relevant_chunks.__name__ == "select_relevant_chunks"
```

- [ ] **Step 2: 运行测试并确认 context 包尚不存在**

Run: `cd backend && uv run pytest tests/test_module_layout.py -v`

Expected: FAIL，提示 `deeptrace.context` 不存在。

- [ ] **Step 3: 拆分 embedding.py**

- `embeddings.py` 保存 `CompressionRuntime`。
- `chunking.py` 保存 `chunk_document`，从 `embeddings.py` 导入 runtime。
- `retrieval.py` 保存 `ChunkSelection`、`select_relevant_chunks`、`is_repeated_query`、`note_embedding_text`、`retrieve_notes`。

`retrieval.py` 继续使用归一化向量点积和 `np.maximum`，不得改变 `0.45`、`0.85`、top-k、稳定排序和相邻块扩展语义。

- [ ] **Step 4: 迁移压缩服务**

把压缩模型、请求、JSON repair、抽取式降级与 `CompressionService` 迁入 `context/compression.py`。`CompressionService._messages` 改为调用：

```python
return build_compression_messages(
    active_query=request.active_query,
    title=request.document.title,
    url=request.document.final_url,
    chunks=[(chunk.index, chunk.text) for chunk in request.selection.chunks],
)
```

保持两次尝试、有界信号量、`asyncio.gather(return_exceptions=True)`、usage 累加及按 `order` 排序不变。

- [ ] **Step 5: 更新依赖与测试路径**

更新 `agent.py`、`nodes.py` 到 `deeptrace.context` 新接口；移动两份测试并更新导入。删除 `embedding.py`、`compression.py`，`context/__init__.py` 显式导出编排层所需接口。

- [ ] **Step 6: 运行上下文回归测试**

Run: `cd backend && uv run pytest tests/test_module_layout.py tests/context -v`

Expected: PASS；真实本地 BGE-M3 测试继续验证双查询 max 与无关页短路。

- [ ] **Step 7: 提交 context 迁移**

```bash
git add backend/src/deeptrace/context backend/src/deeptrace/embedding.py backend/src/deeptrace/compression.py backend/src/deeptrace/agent.py backend/src/deeptrace/nodes.py backend/tests/context backend/tests/test_embedding.py backend/tests/test_compression.py backend/tests/test_module_layout.py
git commit -m "refactor: organize context processing"
```

### Task 4: 建立 orchestration 与 agent 子包

**Files:**
- Create: `backend/src/deeptrace/orchestration/__init__.py`
- Create: `backend/src/deeptrace/orchestration/graph.py`
- Create: `backend/src/deeptrace/orchestration/nodes.py`
- Create: `backend/src/deeptrace/orchestration/state.py`
- Create: `backend/src/deeptrace/agent/__init__.py`
- Create: `backend/src/deeptrace/agent/service.py`
- Modify: `backend/src/deeptrace/__init__.py`
- Modify: `backend/src/deeptrace/cli.py`
- Delete: `backend/src/deeptrace/graph.py`
- Delete: `backend/src/deeptrace/nodes.py`
- Delete: `backend/src/deeptrace/state.py`
- Delete: `backend/src/deeptrace/agent.py`
- Move: `backend/tests/test_graph.py` → `backend/tests/orchestration/test_graph.py`
- Move: `backend/tests/test_state.py` → `backend/tests/orchestration/test_state.py`
- Modify: `backend/tests/test_module_layout.py`

**Interfaces:**
- Produces: `GraphState`、`merge_dicts`、`append_unique`。
- Produces: `ResearchNodes`、`ToolCallResult`、`build_tool_messages`、`keep_recent_tool_turns`、`select_agent_model_mode`、`build_unverified_finalization`。
- Produces: `build_research_graph()` 和 `route_after_agent(state)`。
- Produces: `AgentResult`、`ResearchAgent`、`build_real_agent(settings, on_event=None)`。

- [ ] **Step 1: 扩展公共入口测试**

在 `test_module_layout.py` 增加：

```python
from deeptrace import AgentResult, ResearchAgent, build_real_agent
from deeptrace.orchestration import GraphState, ResearchNodes, build_research_graph


def test_public_agent_and_orchestration_interfaces() -> None:
    assert AgentResult.__name__ == "AgentResult"
    assert ResearchAgent.__name__ == "ResearchAgent"
    assert callable(build_real_agent)
    assert GraphState.__name__ == "GraphState"
    assert ResearchNodes.__name__ == "ResearchNodes"
    assert callable(build_research_graph)
```

- [ ] **Step 2: 运行测试并确认新编排包尚不存在**

Run: `cd backend && uv run pytest tests/test_module_layout.py -v`

Expected: FAIL，提示 `deeptrace.orchestration` 不存在。

- [ ] **Step 3: 迁移 State、节点和图**

将三个模块内容迁入 `orchestration/` 并更新到新 `models`、`context`、`tools`、`prompts` 导入。`graph.py` 继续通过 `RunnableConfig.configurable.service` 注入 `ResearchNodes`，保持固定 `agent → tools → agent` 拓扑不变。

`orchestration/__init__.py` 显式导出 `GraphState`、reducers、`ResearchNodes`、节点纯函数、`build_research_graph` 与 `route_after_agent`。

- [ ] **Step 4: 迁移 Agent 门面并稳定包根 API**

把 `agent.py` 迁入 `agent/service.py`。`agent/__init__.py` 和包根 `deeptrace/__init__.py` 都只导出：

```python
from deeptrace.agent.service import AgentResult, ResearchAgent, build_real_agent

__all__ = ["AgentResult", "ResearchAgent", "build_real_agent"]
```

`cli.py` 改为 `from deeptrace import build_real_agent`，配置从 `deeptrace.config` 导入。删除四个旧顶层模块。

- [ ] **Step 5: 移动编排测试并更新导入**

`test_graph.py` 从 `deeptrace.orchestration` 与 `deeptrace.prompts.research` 导入；`test_state.py` 从 `deeptrace.orchestration.state` 导入 reducers。测试断言不改变。

- [ ] **Step 6: 运行编排与入口回归测试**

Run: `cd backend && uv run pytest tests/test_module_layout.py tests/orchestration -v`

Expected: PASS。

Run: `cd backend && uv run python -c "from deeptrace import AgentResult, ResearchAgent, build_real_agent; print('public api ok')"`

Expected: 输出 `public api ok`。

- [ ] **Step 7: 提交编排与入口迁移**

```bash
git add backend/src/deeptrace/orchestration backend/src/deeptrace/agent backend/src/deeptrace/graph.py backend/src/deeptrace/nodes.py backend/src/deeptrace/state.py backend/src/deeptrace/agent.py backend/src/deeptrace/__init__.py backend/src/deeptrace/cli.py backend/tests/orchestration backend/tests/test_graph.py backend/tests/test_state.py backend/tests/test_module_layout.py
git commit -m "refactor: organize orchestration and agent entrypoint"
```

### Task 5: 迁移 observability、清理旧路径并更新文档

**Files:**
- Create: `backend/src/deeptrace/observability/__init__.py`
- Create: `backend/src/deeptrace/observability/token_metrics.py`
- Modify: `backend/src/deeptrace/orchestration/nodes.py`
- Modify: `backend/src/deeptrace/agent/service.py`
- Modify: `backend/src/deeptrace/cli.py`
- Delete: `backend/src/deeptrace/token_metrics.py`
- Move: `backend/tests/test_token_metrics.py` → `backend/tests/observability/test_token_metrics.py`
- Modify: `backend/tests/test_module_layout.py`
- Modify: `backend/README.md`
- Modify: `docs/superpowers/specs/2026-08-31-deeptrace-module-layout-design.md`
- Modify: `docs/roadmap/deeptrace-evolution.md`

**Interfaces:**
- Produces: `TokenEstimator`、`TokenLedger`、`calculate_round_metrics`、`format_round_metrics`、`format_token_summary`。
- Preserves: `uv run deeptrace "问题"`、包根公共 API、现有测试行为与真实研究闭环。

- [ ] **Step 1: 增加 observability 导入测试**

在 `test_module_layout.py` 增加：

```python
from deeptrace.observability import (
    TokenEstimator,
    TokenLedger,
    calculate_round_metrics,
    format_round_metrics,
    format_token_summary,
)


def test_observability_package_exposes_token_interfaces() -> None:
    assert TokenEstimator.__name__ == "TokenEstimator"
    assert TokenLedger.__name__ == "TokenLedger"
    assert callable(calculate_round_metrics)
    assert callable(format_round_metrics)
    assert callable(format_token_summary)
```

- [ ] **Step 2: 运行测试并确认 observability 尚不存在**

Run: `cd backend && uv run pytest tests/test_module_layout.py -v`

Expected: FAIL，提示 `deeptrace.observability` 不存在。

- [ ] **Step 3: 迁移 Token 指标实现**

将 `token_metrics.py` 原样迁入 `observability/token_metrics.py`，只把模型导入调整为 `deeptrace.models`。`observability/__init__.py` 显式导出五个公共接口，更新节点、Agent 和 CLI 导入后删除旧文件。移动 Token 测试并保持断言不变。

- [ ] **Step 4: 更新 README 与阶段状态**

README 用目标目录树替换旧文件列表，并增加：

```text
models/config/prompts → context/tools/observability
→ orchestration → agent → cli
```

说明 `prompts/` 是唯一长提示词管理位置，并记录后续模块只在对应阶段实现时创建。把模块化设计文档状态改为“已完成”，路线图补充“阶段 2 代码已完成模块化整理”。

- [ ] **Step 5: 检查旧内部路径和提示词残留**

Run:

```powershell
rg -n "deeptrace\.(agent|compression|embedding|fetching|graph|models|nodes|state|token_metrics|tools|urls)(\s|\.|$)" backend/src backend/tests
```

Expected: 只允许新的包导入，例如 `deeptrace.agent.service`、`deeptrace.models` 和 `deeptrace.tools.scraper`；不得出现已删除顶层文件路径。

Run:

```powershell
rg -n '你是 DeepTrace|研究预算已经到达|你是研究资料压缩器' backend/src/deeptrace -g '*.py'
```

Expected: 匹配只出现在 `backend/src/deeptrace/prompts/`。

- [ ] **Step 6: 运行完整非真实回归测试**

Run: `cd backend && uv run pytest -v -m "not real"`

Expected: PASS，当前 19 项非真实测试及新增模块导入契约全部通过。

- [ ] **Step 7: 运行一次真实 CLI 冒烟**

Run: `cd backend && uv run deeptrace "今年字节跳动 Agent 开发岗位常见要求是什么？请搜索并抓取来源。"`

Expected: 完成真实模型调用、Tavily 搜索、至少一次网页抓取或给出明确的外部失败原因；成功时输出研究报告、来源和 Token 统计。不得打印 API Key、Cookie 或 Authorization。

- [ ] **Step 8: 提交最终迁移**

```bash
git add backend/src/deeptrace/observability backend/src/deeptrace/token_metrics.py backend/src/deeptrace/orchestration/nodes.py backend/src/deeptrace/agent/service.py backend/src/deeptrace/cli.py backend/tests/observability backend/tests/test_token_metrics.py backend/tests/test_module_layout.py backend/README.md docs/superpowers/specs/2026-08-31-deeptrace-module-layout-design.md docs/roadmap/deeptrace-evolution.md
git commit -m "refactor: complete modular package layout"
```

## Final Verification

- [ ] `rg --files backend/src/deeptrace` 只显示目标目录中的实现，不再显示旧顶层内部模块。
- [ ] `uv run pytest -v -m "not real"` 全部通过。
- [ ] 包根 `AgentResult`、`ResearchAgent`、`build_real_agent` 可导入。
- [ ] 长提示词只位于 `prompts/`。
- [ ] 一次真实 CLI 研究闭环成功或留下明确、可解释的外部失败信息。
- [ ] `git status --short` 不包含密钥、缓存、模型文件或本次范围外的新改动。
