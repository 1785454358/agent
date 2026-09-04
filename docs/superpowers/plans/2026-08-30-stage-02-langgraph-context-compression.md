# DeepTrace Stage 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把阶段 1 的 CLI 单 Agent 迁移到 LangGraph，并加入 BGE-M3 上下文压缩、可靠抓取降级链和逐轮 Token 节省统计。

**Status:** 已完成（2026-08-31），本文仅作为阶段 2 的实施记录保留。

**Architecture:** LangGraph 负责显式状态和节点路由，主 Agent 每轮只接收相关 ResearchNote 与最近一组合法工具消息。原始网页保存在 State 文档区，向量和 Token 基线账本保存在单次运行的进程内 runtime，避免把 numpy 数组和重复正文写入 checkpoint。

**Tech Stack:** Python 3.11、LangGraph、LangChain Core、ChatOpenAI、Tavily、HTTPX、Trafilatura、BeautifulSoup、Playwright、SentenceTransformers/BGE-M3、Pydantic、json-repair、tiktoken、pytest。

**Spec:** `docs/superpowers/specs/2026-08-30-stage-02-langgraph-context-compression-design.md`

## Global Constraints

- 正式代码只写入 `backend/`，不恢复或维护 `reference_implementation/`。
- 本地 Embedding 模型固定从 `D:\Dev\Models\bge-m3` 加载，路径可通过环境变量覆盖。
- chunk 目标大小为 800 token，重叠 100 token，Embedding batch size 为 8。
- 相关性固定使用 `max(sim(user_query, item), sim(active_query, item))`。
- 初始整页无关阈值为 `0.45`，压缩并发度为 3。
- 正文至少同时达到 500 字符和 200 token，否则进入下一抓取级别。
- 初始软步数上限为 8，硬上限为 12，查询循环阈值为 `0.85`。
- Token 对照估算统一使用 `cl100k_base`，Provider usage 单独展示。
- 原始网页正文禁止进入主 Agent 对话，压缩最终失败时回填筛选后的原文块。
- 不使用 Fake、Mock、Stub、预录 LLM/Tavily 响应或离线替代。单元测试覆盖纯函数，Embedding 测试使用真实本地 BGE-M3，端到端冒烟使用真实 API Key。
- 代码保留必要中文注释；阶段 2 只做必要测试和一次真实冒烟，不进行大规模评测。

---

## File Map

| 文件 | 变更 | 单一职责 |
|---|---|---|
| `backend/pyproject.toml` | 修改 | 声明阶段 2 运行与测试依赖 |
| `backend/src/deeptrace/config.py` | 修改 | 加载并校验阶段 2 配置 |
| `backend/src/deeptrace/models.py` | 新建 | 定义文档、块、笔记、工具结果和 Token 指标模型 |
| `backend/src/deeptrace/state.py` | 新建 | 定义 GraphState 与 reducer |
| `backend/src/deeptrace/urls.py` | 新建 | URL 抓取前规范化和抓取后身份判断 |
| `backend/src/deeptrace/fetching.py` | 新建 | 异步抓取、正文提取、质量判断和 Playwright 降级 |
| `backend/src/deeptrace/embedding.py` | 新建 | BGE-M3 加载、分块、批量向量化、相似度和运行时注册表 |
| `backend/src/deeptrace/compression.py` | 新建 | 双查询筛选、结构化笔记、JSON 修复、降级和 note 召回 |
| `backend/src/deeptrace/token_metrics.py` | 新建 | Token 估算、阶段 1 反事实账本、逐轮与累计指标 |
| `backend/src/deeptrace/tools.py` | 修改 | 保留工具 schema 和搜索，抓取委托给新抓取服务 |
| `backend/src/deeptrace/nodes.py` | 新建 | 实现 LangGraph 各节点及 fan-out/fan-in |
| `backend/src/deeptrace/graph.py` | 新建 | 构建、连接并编译 StateGraph |
| `backend/src/deeptrace/agent.py` | 修改 | 对外提供 ResearchAgent 门面与 AgentResult |
| `backend/src/deeptrace/cli.py` | 修改 | 组装真实依赖，输出进度、来源和 Token 汇总 |
| `backend/README.md` | 修改 | 简述安装、配置、运行和模块职责 |
| `backend/tests/*.py` | 新建 | 按上述边界验证纯函数、本地模型和真实冒烟 |

### Task 1: 依赖、配置、数据模型与 State

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `backend/src/deeptrace/config.py`
- Create: `backend/src/deeptrace/models.py`
- Create: `backend/src/deeptrace/state.py`
- Create: `backend/tests/test_config.py`
- Create: `backend/tests/test_state.py`

**Interfaces:**
- Produces: `Settings` 的阶段 2 字段。
- Produces: `PendingFetch`、`RawDocument`、`DocumentChunk`、`ResearchNote`、`CompressionOutcome`、`TokenUsage`、`RoundTokenMetrics`。
- Produces: `merge_dicts(left, right)`、`append_unique(left, right)` 和 `GraphState`。

- [ ] **Step 1: 写配置和 reducer 的失败测试**

```python
# backend/tests/test_state.py
from deeptrace.state import append_unique, merge_dicts

def test_merge_dicts_preserves_old_entries_and_overwrites_same_key() -> None:
    assert merge_dicts({"a": 1, "b": 2}, {"b": 3, "c": 4}) == {
        "a": 1, "b": 3, "c": 4
    }

def test_append_unique_keeps_first_seen_order() -> None:
    assert append_unique(["q1", "q2"], ["q2", "q3"]) == ["q1", "q2", "q3"]
```

```python
# backend/tests/test_config.py
from pathlib import Path
from deeptrace.config import Settings

def test_stage_two_defaults(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "real-value-not-used")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.com/v1")
    monkeypatch.setenv("OPENAI_MODEL", "model")
    monkeypatch.setenv("TAVILY_API_KEY", "real-value-not-used")
    settings = Settings.from_env()
    assert settings.embedding_model_path == Path(r"D:\Dev\Models\bge-m3")
    assert settings.min_relevance_score == 0.45
    assert settings.soft_max_steps == 8
    assert settings.hard_max_steps == 12
```

- [ ] **Step 2: 运行测试并确认因模块或字段缺失而失败**

Run: `cd backend && uv run pytest tests/test_state.py tests/test_config.py -v`

Expected: FAIL，提示 `deeptrace.state` 不存在或 `Settings` 缺少阶段 2 字段。

- [ ] **Step 3: 添加依赖和配置**

Run:

```bash
cd backend
uv add "langgraph>=1.0" "langchain-openai>=1.0.1" "sentence-transformers>=5.0" "beautifulsoup4>=4.13" "playwright>=1.55" "tiktoken>=0.11" "json-repair>=0.50" "pydantic>=2.10"
uv run playwright install chromium
```

在 `[tool.pytest.ini_options]` 中注册 `real` marker，保证真实冒烟可以和纯函数测试分开执行。

在 `Settings` 中加入以下字段并使用现有 `_required`、`_bounded_int` 风格校验：

```python
embedding_model_path: Path = Path(r"D:\Dev\Models\bge-m3")
min_relevance_score: float = 0.45
embedding_batch_size: int = 8
compression_concurrency: int = 3
min_extracted_chars: int = 500
min_extracted_tokens: int = 200
soft_max_steps: int = 8
hard_max_steps: int = 12
query_loop_threshold: float = 0.85
token_encoding: str = "cl100k_base"
```

`from_env()` 必须检查模型目录存在，并保证 `soft_max_steps <= hard_max_steps`。

- [ ] **Step 4: 实现模型与 State**

```python
# backend/src/deeptrace/state.py
from typing import Annotated, Any, TypedDict
from langchain_core.messages import BaseMessage
from deeptrace.models import (
    DocumentChunk, PendingFetch, RawDocument, ResearchNote, RoundTokenMetrics
)

def merge_dicts(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    return {**left, **right}

def append_unique(left: list[str], right: list[str]) -> list[str]:
    return list(dict.fromkeys([*left, *right]))

class GraphState(TypedDict):
    user_query: str
    active_query: str
    messages: list[BaseMessage]
    documents: Annotated[dict[str, RawDocument], merge_dicts]
    chunks: Annotated[dict[str, DocumentChunk], merge_dicts]
    notes: Annotated[dict[str, ResearchNote], merge_dicts]
    queries: Annotated[list[str], append_unique]
    pending_fetches: list[PendingFetch]
    pending_tool_order: list[str]
    tool_outputs: Annotated[dict[str, str], merge_dicts]
    events: Annotated[list[str], list.__add__]
    token_metrics: Annotated[list[RoundTokenMetrics], list.__add__]
    step_count: int
    extension_granted: bool
    recent_new_note_count: int
    unresolved_gaps: list[str]
    final_answer: str
```

`models.py` 使用 Pydantic `BaseModel` 和 `ScraperUsed(StrEnum)`。核心模型至少包含以下字段。

```python
class PendingFetch(BaseModel):
    tool_call_id: str
    url: str
    active_query: str
    order: int

class ScraperUsed(StrEnum):
    HTTPX_TRAFILATURA = "httpx_trafilatura"
    HTTPX_BS4 = "httpx_bs4"
    PLAYWRIGHT_TRAFILATURA = "playwright_trafilatura"
    PLAYWRIGHT_BS4 = "playwright_bs4"

class RawDocument(BaseModel):
    doc_id: str
    requested_url: str
    final_url: str
    canonical_url: str | None
    title: str
    content: str
    content_hash: str
    fetched_at: datetime
    scraper_used: ScraperUsed
    status: Literal["success", "irrelevant", "failed"]
    error: str | None = None

class DocumentChunk(BaseModel):
    chunk_id: str
    doc_id: str
    index: int
    text: str
    token_count: int
    char_start: int
    char_end: int

class ResearchNote(BaseModel):
    note_id: str
    doc_id: str
    active_query: str
    title: str
    key_points: list[str]
    evidence_snippets: list[str]
    source_url: str
    relevance_score: float
    compression_status: Literal["compressed", "extractive_fallback", "irrelevant"]
    error: str | None = None

class TokenUsage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0

class ContextAudit(BaseModel):
    round_index: int
    input_tokens: int
    raw_content_match_count: int

class CompressionOutcome(BaseModel):
    tool_call_id: str
    note: ResearchNote | None
    error: str | None
    order: int
```

RoundTokenMetrics 按设计文档定义轮次、基线、实际值、压缩 usage、Provider usage、毛节省和净节省字段。所有 URL、顺序、状态和 Token 字段都显式声明，不使用自由形状字典代替核心模型。

- [ ] **Step 5: 运行测试并提交**

Run: `cd backend && uv run pytest tests/test_state.py tests/test_config.py -v`

Expected: PASS。

```bash
git add backend/pyproject.toml backend/uv.lock backend/src/deeptrace/config.py backend/src/deeptrace/models.py backend/src/deeptrace/state.py backend/tests/test_config.py backend/tests/test_state.py
git commit -m "feat: add stage two state and models"
```

### Task 2: URL 身份与可靠抓取降级链

**Files:**
- Create: `backend/src/deeptrace/urls.py`
- Create: `backend/src/deeptrace/fetching.py`
- Modify: `backend/src/deeptrace/tools.py`
- Create: `backend/tests/test_urls.py`
- Create: `backend/tests/test_fetching.py`

**Interfaces:**
- Produces: `normalize_url_before_fetch(url: str) -> str`。
- Produces: `resolve_document_identity(final_url, canonical_url, content_hash) -> str`。
- Produces: `is_usable_text(text, count_tokens, min_chars, min_tokens) -> bool`。
- Produces: `AsyncWebFetcher.fetch(url: str) -> RawDocument` 和 `AsyncWebFetcher.aclose() -> None`。

- [ ] **Step 1: 写 URL 与提取质量失败测试**

```python
def test_normalize_url_removes_tracking_and_sorts_query() -> None:
    raw = "HTTPS://Example.COM/a/../news/?utm_source=x&b=2&a=1#top"
    assert normalize_url_before_fetch(raw) == "https://example.com/news?a=1&b=2"

def test_mobile_host_is_not_merged_without_content_identity() -> None:
    desktop = resolve_document_identity("https://example.com/a", None, "hash-a")
    mobile = resolve_document_identity("https://m.example.com/a", None, "hash-b")
    assert desktop != mobile

def test_text_must_pass_both_minimums() -> None:
    assert not is_usable_text("字" * 600, lambda _: 150, 500, 200)
    assert is_usable_text("字" * 600, lambda _: 220, 500, 200)
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `cd backend && uv run pytest tests/test_urls.py tests/test_fetching.py -v`

Expected: FAIL，提示 URL 或抓取模块不存在。

- [ ] **Step 3: 实现 URL 规范化和页面身份**

`normalize_url_before_fetch` 删除 fragment、默认端口和 `utm_*`、`gclid`、`fbclid`，规范化点段与尾部斜杠，并稳定排序 query。HTTP/HTTPS 与移动子域不在抓取前合并。

```python
def resolve_document_identity(
    final_url: str,
    canonical_url: str | None,
    content_hash: str,
) -> str:
    if content_hash:
        return hashlib.sha256(f"content:{content_hash}".encode()).hexdigest()
    identity_url = normalize_url_before_fetch(canonical_url or final_url)
    return hashlib.sha256(f"url:{identity_url}".encode()).hexdigest()
```

- [ ] **Step 4: 实现异步抓取降级链**

```python
class AsyncWebFetcher:
    async def fetch(self, url: str) -> RawDocument:
        normalized = normalize_url_before_fetch(url)
        html, final_url = await self._fetch_httpx(normalized)
        candidates = [
            self._extract_trafilatura(html, final_url),
            self._extract_bs4(html),
        ]
        best = max(candidates, key=lambda item: len(item.text))
        if not self._is_usable(best.text):
            rendered_html, rendered_url = await self._fetch_playwright(normalized)
            rendered = [
                self._extract_trafilatura(rendered_html, rendered_url),
                self._extract_bs4(rendered_html),
            ]
            best = max([best, *rendered], key=lambda item: len(item.text))
            final_url = rendered_url
        return self._to_document(normalized, final_url, html, best)
```

HTTPX 和每次重定向都复用公网 URL 校验；最多跟随 3 次重定向。Playwright 使用 async API，超时后关闭 page，阻断 `image`、`media`、`font`，并在 `aclose()` 中关闭 browser。若浏览器未安装，返回包含安装命令的结构化错误，不吞掉异常。

- [ ] **Step 5: 运行测试并提交**

Run: `cd backend && uv run pytest tests/test_urls.py tests/test_fetching.py -v`

Expected: PASS。

```bash
git add backend/src/deeptrace/urls.py backend/src/deeptrace/fetching.py backend/src/deeptrace/tools.py backend/tests/test_urls.py backend/tests/test_fetching.py
git commit -m "feat: add resilient webpage fetching"
```

### Task 3: BGE-M3 分块、向量注册与双查询召回

**Files:**
- Create: `backend/src/deeptrace/embedding.py`
- Create: `backend/tests/test_embedding.py`

**Interfaces:**
- Produces: `CompressionRuntime(model_path: Path, batch_size: int)`。
- Produces: `chunk_document(document, chunk_tokens=800, overlap_tokens=100) -> list[DocumentChunk]`。
- Produces: `select_relevant_chunks(runtime, chunks, user_query, active_query, top_k, threshold) -> ChunkSelection`。
- Produces: `is_repeated_query(runtime, query, history, threshold=0.85) -> bool`。

- [ ] **Step 1: 使用真实本地 BGE-M3 写失败测试**

```python
MODEL_PATH = Path(r"D:\Dev\Models\bge-m3")

def test_dual_query_max_fusion_keeps_new_direction() -> None:
    runtime = CompressionRuntime(MODEL_PATH, batch_size=8)
    def chunk(index: int, text: str) -> DocumentChunk:
        return DocumentChunk(
            chunk_id=f"doc:{index}",
            doc_id="doc",
            index=index,
            text=text,
            token_count=runtime.count_tokens(text),
            char_start=0,
            char_end=len(text),
        )
    chunks = [
        chunk(0, "公司整体招聘介绍"),
        chunk(1, "Agent 岗位要求掌握 LangGraph 与工具调用"),
        chunk(2, "食谱与烹饪技巧"),
    ]
    selection = select_relevant_chunks(
        runtime=runtime,
        chunks=chunks,
        user_query="今年字节跳动招聘要求",
        active_query="Agent 开发需要哪些框架经验",
        top_k=2,
        threshold=0.45,
    )
    assert "LangGraph" in " ".join(item.text for item in selection.chunks)
    assert selection.top1_fused_score == max(
        selection.top1_user_score, selection.top1_active_score
    )
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `cd backend && uv run pytest tests/test_embedding.py -v`

Expected: FAIL，提示 `deeptrace.embedding` 不存在。首次加载真实模型可能需要数十秒。

- [ ] **Step 3: 实现运行时注册表和分块**

```python
class CompressionRuntime:
    def __init__(self, model_path: Path, batch_size: int) -> None:
        self.model = SentenceTransformer(str(model_path))
        self.tokenizer = self.model.tokenizer
        self.batch_size = batch_size
        self.chunk_vectors: dict[str, np.ndarray] = {}
        self.query_vectors: dict[str, np.ndarray] = {}

    def embed(self, texts: list[str]) -> np.ndarray:
        return self.model.encode(
            texts,
            batch_size=self.batch_size,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
```

`chunk_document` 按 tokenizer token IDs 切分并 decode，记录 token 数、块序号和字符范围。新增文档的 chunks 合并成一次 `embed()` 调用并写入 `chunk_vectors`。

- [ ] **Step 4: 实现 max 融合、邻块扩展和循环检测**

```python
user_scores = chunk_matrix @ runtime.query_vector(user_query)
active_scores = chunk_matrix @ runtime.query_vector(active_query)
fused_scores = np.maximum(user_scores, active_scores)
```

取 top-k 后加入前后各一个相邻块，按 `(doc_id, index)` 去重并恢复原顺序。若 top-1 fused 低于阈值，返回 `is_relevant=False` 和空 chunks。重复查询使用同一归一化向量点积，`max_similarity > 0.85` 返回 True。

- [ ] **Step 5: 运行测试并提交**

Run: `cd backend && uv run pytest tests/test_embedding.py -v`

Expected: PASS。

```bash
git add backend/src/deeptrace/embedding.py backend/tests/test_embedding.py
git commit -m "feat: add bge context retrieval"
```

### Task 4: ResearchNote 压缩、修复、降级与检索

**Files:**
- Create: `backend/src/deeptrace/compression.py`
- Create: `backend/tests/test_compression.py`

**Interfaces:**
- Consumes: `CompressionRuntime`、`ChunkSelection`、`ResearchNote`。
- Produces: `parse_note_json(raw: str) -> ResearchNotePayload`。
- Produces: `build_extractive_note(document, selection, active_query, error) -> ResearchNote`。
- Produces: `CompressionService.compress_one(...) -> CompressionOutcome`。
- Produces: `retrieve_notes(runtime, notes, user_query, active_query, top_k=8) -> list[ResearchNote]`。

- [ ] **Step 1: 写解析降级和新方向召回失败测试**

```python
def test_invalid_json_falls_back_to_selected_chunks() -> None:
    document = RawDocument(
        doc_id="doc-1",
        requested_url="https://example.com/job",
        final_url="https://example.com/job",
        canonical_url=None,
        title="Agent 招聘",
        content="Agent 岗位要求掌握 LangGraph 与工具调用",
        content_hash="hash",
        fetched_at=datetime.now(timezone.utc),
        scraper_used=ScraperUsed.HTTPX_TRAFILATURA,
        status="success",
    )
    selected = DocumentChunk(
        chunk_id="doc-1:0", doc_id="doc-1", index=0,
        text=document.content, token_count=12, char_start=0,
        char_end=len(document.content),
    )
    selection = ChunkSelection(
        chunks=[selected], is_relevant=True,
        top1_user_score=0.51, top1_active_score=0.82,
        top1_fused_score=0.82,
    )
    note = build_extractive_note(
        document, selection, "Agent 框架要求", "invalid_json"
    )
    assert note.compression_status == "extractive_fallback"
    assert selection.chunks[0].text in note.evidence_snippets

def test_note_embedding_text_contains_evidence() -> None:
    note = ResearchNote(
        note_id="note-1", doc_id="doc-1", active_query="Agent 框架要求",
        title="Agent 招聘", key_points=["要求掌握 LangGraph"],
        evidence_snippets=["熟悉工具调用"], source_url="https://example.com/job",
        relevance_score=0.82, compression_status="compressed",
    )
    text = note_embedding_text(note)
    assert note.title in text
    assert note.key_points[0] in text
    assert note.evidence_snippets[0] in text
```

再用真实 BGE-M3 构造一条早期宽泛笔记和一条后期 LangGraph 笔记，验证 active query 能把后者排到前面。

- [ ] **Step 2: 运行测试并确认失败**

Run: `cd backend && uv run pytest tests/test_compression.py -v`

Expected: FAIL，提示压缩函数不存在。

- [ ] **Step 3: 实现结构化解析和无损降级**

```python
def parse_note_json(raw: str) -> ResearchNotePayload:
    try:
        return ResearchNotePayload.model_validate_json(raw)
    except ValidationError:
        repaired = json_repair.loads(raw)
        return ResearchNotePayload.model_validate(repaired)
```

`build_extractive_note` 必须把所有入选块放进 `evidence_snippets`，并保留标题、URL、top-1 分数和错误原因。

- [ ] **Step 4: 实现真实 LLM 压缩和有界并发**

```python
async def compress_one(self, request: CompressionRequest) -> CompressionOutcome:
    if not request.selection.is_relevant:
        return self._irrelevant_outcome(request)
    async with self._semaphore:
        for attempt in range(2):
            try:
                message = await self._model.ainvoke(self._prompt(request))
                payload = parse_note_json(str(message.content))
                return self._success_outcome(request, payload, message.usage_metadata)
            except Exception as exc:
                last_error = type(exc).__name__
    note = build_extractive_note(
        request.document, request.selection, request.active_query, last_error
    )
    return CompressionOutcome(
        tool_call_id=request.tool_call_id,
        note=note,
        error=last_error,
        order=request.order,
    )
```

`compress_many` 使用 `asyncio.gather(..., return_exceptions=True)`，把任务级异常转成对应页面的抽取式结果，并按 `order` 排序。

- [ ] **Step 5: 运行测试并提交**

Run: `cd backend && uv run pytest tests/test_compression.py -v`

Expected: PASS。

```bash
git add backend/src/deeptrace/compression.py backend/tests/test_compression.py
git commit -m "feat: add research note compression"
```

### Task 5: 阶段 1 反事实 Token 账本

**Files:**
- Create: `backend/src/deeptrace/token_metrics.py`
- Create: `backend/tests/test_token_metrics.py`

**Interfaces:**
- Produces: `TokenEstimator(encoding_name: str)`。
- Produces: `TokenLedger.record_assistant(...)、record_search_tool(...)、record_fetch_pair(...)、finish_round(...)`。
- Produces: `format_round_metrics(metrics) -> str` 和 `format_token_summary(metrics) -> str`。

- [ ] **Step 1: 写公式和累积基线失败测试**

```python
def test_round_metrics_subtract_compression_cost() -> None:
    metrics = calculate_round_metrics(
        round_index=4,
        baseline_context_tokens=32_180,
        actual_context_tokens=8_420,
        compression_input_tokens=1_800,
        compression_output_tokens=340,
    )
    assert metrics.gross_saved_tokens == 23_760
    assert metrics.net_saved_tokens == 21_620
    assert metrics.gross_saving_ratio == pytest.approx(0.7383, abs=0.0001)
    assert metrics.net_saving_ratio == pytest.approx(0.6718, abs=0.0001)

def test_baseline_accumulates_old_raw_pages() -> None:
    ledger.record_fetch_pair(raw_payload="原文一" * 1000, note_payload="笔记一")
    first = ledger.baseline_payload_tokens
    ledger.record_fetch_pair(raw_payload="原文二" * 1000, note_payload="笔记二")
    assert ledger.baseline_payload_tokens > first
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `cd backend && uv run pytest tests/test_token_metrics.py -v`

Expected: FAIL，提示 Token 指标模块不存在。

- [ ] **Step 3: 实现 estimator 和账本**

```python
class TokenLedger:
    def record_fetch_pair(self, raw_payload: str, note_payload: str) -> None:
        raw = self.estimator.count(raw_payload)
        note = self.estimator.count(note_payload)
        self.baseline_payload_tokens += raw
        self.actual_note_payload_tokens += note
        self.page_metrics.append(PageCompressionMetrics(
            raw_tool_payload_tokens=raw,
            note_tool_payload_tokens=note,
            compression_ratio=1 - note / max(raw, 1),
        ))

    def finish_round(
        self,
        round_index: int,
        actual_messages: list[BaseMessage],
        compression_usage: TokenUsage,
        provider_usage: TokenUsage | None,
    ) -> RoundTokenMetrics:
        actual = self.estimator.count_messages(actual_messages)
        baseline = self.baseline_fixed_tokens + self.baseline_payload_tokens
        return calculate_round_metrics(
            round_index, baseline, actual,
            compression_usage.input_tokens, compression_usage.output_tokens,
            provider_usage,
        )
```

`baseline_fixed_tokens` 随阶段 1 等价的 system/user/assistant/search-tool 消息累积；fetch 工具消息只把 raw payload 加入基线。实际值每轮直接统计送入 `ChatOpenAI.ainvoke()` 的消息。不得把本地 embedding token 扣进 API 净节省。

- [ ] **Step 4: 运行测试并提交**

Run: `cd backend && uv run pytest tests/test_token_metrics.py -v`

Expected: PASS。

```bash
git add backend/src/deeptrace/token_metrics.py backend/tests/test_token_metrics.py
git commit -m "feat: measure context token savings"
```

### Task 6: LangGraph 节点、工具映射与步数预算

**Files:**
- Create: `backend/src/deeptrace/nodes.py`
- Create: `backend/src/deeptrace/graph.py`
- Modify: `backend/src/deeptrace/tools.py`
- Create: `backend/tests/test_graph.py`

**Interfaces:**
- Consumes: Settings、ChatOpenAI、TavilyClient、AsyncWebFetcher、CompressionRuntime、CompressionService、TokenLedger。
- Produces: `GraphDependencies`、`ResearchNodes`、`build_research_graph(deps) -> CompiledStateGraph`。
- Produces: `should_route_after_agent(state)`、`should_route_after_dispatch(state)`、`allow_extension(state, runtime, settings) -> bool`。

- [ ] **Step 1: 写 tool_call_id 映射和路由失败测试**

```python
def test_tool_messages_follow_original_call_order() -> None:
    note_a = ResearchNote(
        note_id="a", doc_id="doc-a", active_query="q", title="A 页",
        key_points=["A"], evidence_snippets=["A 证据"],
        source_url="https://a.example", relevance_score=0.8,
        compression_status="compressed",
    )
    note_b = ResearchNote(
        note_id="b", doc_id="doc-b", active_query="q", title="B 页",
        key_points=["B"], evidence_snippets=["B 证据"],
        source_url="https://b.example", relevance_score=0.8,
        compression_status="compressed",
    )
    outcomes = [
        CompressionOutcome(tool_call_id="call-b", note=note_b, error=None, order=1),
        CompressionOutcome(tool_call_id="call-a", note=note_a, error=None, order=0),
    ]
    messages = build_tool_messages(["call-a", "call-b"], outcomes)
    assert [message.tool_call_id for message in messages] == ["call-a", "call-b"]
    assert "A 页" in messages[0].content
    assert "B 页" in messages[1].content

def test_repeated_query_cannot_extend() -> None:
    runtime = CompressionRuntime(Path(r"D:\Dev\Models\bge-m3"), batch_size=8)
    settings = Settings.from_env()
    state: GraphState = {
        **initial_state("调研招聘要求"),
        "step_count": 8,
        "queries": ["字节 Agent 岗位要求"],
        "active_query": "字节 Agent 岗位要求",
        "extension_granted": False,
        "recent_new_note_count": 1,
        "unresolved_gaps": ["缺少任职要求原文"],
    }
    assert not allow_extension(state, runtime, settings)
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `cd backend && uv run pytest tests/test_graph.py -v`

Expected: FAIL，提示图节点或映射函数不存在。

- [ ] **Step 3: 实现节点依赖和有界主 Agent 上下文**

```python
@dataclass
class GraphDependencies:
    settings: Settings
    model: ChatOpenAI
    tavily: TavilyClient
    fetcher: AsyncWebFetcher
    runtime: CompressionRuntime
    compressor: CompressionService
    token_ledger: TokenLedger
    on_event: Callable[[str], None]

def build_agent_input(state: GraphState, relevant_notes: list[ResearchNote]) -> list[BaseMessage]:
    note_text = render_notes(relevant_notes)
    return [
        SystemMessage(SYSTEM_PROMPT),
        HumanMessage(state["user_query"]),
        SystemMessage(f"当前研究笔记\n{note_text}"),
        *state["messages"],
    ]
```

`state["messages"]` 只保留最近一组 `AIMessage(tool_calls) + ToolMessage`，保证协议合法。agent 节点每轮重新检索 notes，并把真实调用的消息列表交给 TokenLedger 统计。

- [ ] **Step 4: 实现工具 fan-out/fan-in**

`agent` 首次使用 `deps.model.bind_tools(TOOL_SCHEMAS)` 得到带工具模型，后续复用该实例。`dispatch_tools` 读取标准化 `AIMessage.tool_calls`。搜索调用立即执行并写入 `tool_outputs`；抓取调用生成 PendingFetch。PendingFetch 的 active query 取当前批次最近一次搜索 query，没有搜索时回退到 state active query，再回退到 user query。未知工具、参数错误和抓取失败也必须生成对应 ToolMessage。

`fetch_documents` 并发抓取，命中已有 canonical URL 时复用 RawDocument。`prepare_chunks` 只为新文档分块和 embedding，但对复用文档按新 active query 重新筛选。`compress_documents` 按 `doc_id + active_query_hash` 复用已有同角度笔记，其余任务并发生成 CompressionOutcome。`build_tool_messages` 按 `pending_tool_order` 回填后覆盖 `messages`。

- [ ] **Step 5: 构建并编译 StateGraph**

```python
def build_research_graph(deps: GraphDependencies):
    nodes = ResearchNodes(deps)
    graph = StateGraph(GraphState)
    graph.add_node("agent", nodes.agent)
    graph.add_node("dispatch_tools", nodes.dispatch_tools)
    graph.add_node("fetch_documents", nodes.fetch_documents)
    graph.add_node("prepare_chunks", nodes.prepare_chunks)
    graph.add_node("compress_documents", nodes.compress_documents)
    graph.add_node("build_tool_messages", nodes.build_tool_messages)
    graph.add_node("finalize", nodes.finalize)
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", should_route_after_agent)
    graph.add_conditional_edges("dispatch_tools", should_route_after_dispatch)
    graph.add_edge("fetch_documents", "prepare_chunks")
    graph.add_edge("prepare_chunks", "compress_documents")
    graph.add_edge("compress_documents", "build_tool_messages")
    graph.add_edge("build_tool_messages", "agent")
    graph.add_edge("finalize", END)
    return graph.compile()
```

软上限 8 时调用 `allow_extension`，只允许一次；硬上限 12 必须结束。重复查询、没有近期新笔记或没有明确缺口时不延长。

- [ ] **Step 6: 运行测试并提交**

Run: `cd backend && uv run pytest tests/test_graph.py -v`

Expected: PASS。

```bash
git add backend/src/deeptrace/nodes.py backend/src/deeptrace/graph.py backend/src/deeptrace/tools.py backend/tests/test_graph.py
git commit -m "feat: orchestrate research with langgraph"
```

### Task 7: Agent 门面、CLI、中文说明与真实冒烟

**Files:**
- Modify: `backend/src/deeptrace/agent.py`
- Modify: `backend/src/deeptrace/cli.py`
- Modify: `backend/README.md`
- Create: `backend/tests/test_real_stage_two.py`

**Interfaces:**
- Produces: `ResearchAgent.arun(question: str) -> AgentResult`。
- Produces: `ResearchAgent.run(question: str) -> AgentResult` 同步兼容入口。
- CLI 输出最终答案、来源、步骤、每轮 Token 行和累计汇总。

- [ ] **Step 1: 写真实冒烟测试**

```python
@pytest.mark.real
def test_real_research_reports_token_savings() -> None:
    settings = Settings.from_env()
    agent = build_real_agent(settings)
    result = agent.run("调研当前 Agent 开发岗位常见要求，抓取来源后简要总结。")
    assert result.status in {"completed", "max_steps_reached"}
    assert result.sources
    assert result.token_metrics
    assert any(item.gross_saved_tokens > 0 for item in result.token_metrics)
    assert all(
        audit.raw_content_match_count == 0
        for audit in result.context_audits
    )
```

- [ ] **Step 2: 运行冒烟测试并确认入口尚未完成**

Run: `cd backend && uv run pytest tests/test_real_stage_two.py -v -m real`

Expected: FAIL，提示 `build_real_agent`、Token 指标或阶段 2 Agent 接口缺失。

- [ ] **Step 3: 实现 Agent 门面和真实依赖组装**

```python
class ResearchAgent:
    async def arun(self, question: str) -> AgentResult:
        initial = initial_state(question)
        final = await self._graph.ainvoke(initial)
        return AgentResult.from_state(final)

    def run(self, question: str) -> AgentResult:
        return asyncio.run(self.arun(question))
```

`AgentResult` 加入 `token_metrics: list[RoundTokenMetrics]`、`notes: list[ResearchNote]` 和 `context_audits: list[ContextAudit]`。`ContextAudit` 只保存计数，不保存提示词正文。每次调用模型前检查序列化输入中是否完整包含任一 RawDocument.content，并把命中数写入 `raw_content_match_count`。

`build_real_agent(settings)` 创建 `ChatOpenAI(model=..., api_key=..., base_url=..., temperature=0)`、TavilyClient、AsyncWebFetcher、CompressionRuntime、CompressionService、TokenLedger 和 graph。所有资源在运行结束时关闭，Playwright 延迟启动。

- [ ] **Step 4: 更新 CLI Token 输出**

```python
for metric in result.token_metrics:
    print(format_round_metrics(metric))
print(format_token_summary(result.token_metrics))
```

CLI 对配置错误、模型错误、搜索错误、浏览器未安装和抓取部分失败给出中文信息，不打印 API Key、Cookie、Authorization 或完整请求头。

- [ ] **Step 5: 写简洁 README**

`README.md` 只包含以下内容：

1. `uv sync` 与 `uv run playwright install chromium`。
2. 全部环境变量和真实凭据说明。
3. `uv run deeptrace "问题"` 运行命令。
4. 文件与函数职责表。
5. LangGraph 编排、双查询压缩、抓取降级和 Token 指标四段核心说明。
6. 估算 Token 与 Provider usage 的口径差异。

- [ ] **Step 6: 运行全部必要测试**

Run: `cd backend && uv run pytest -v -m "not real"`

Expected: PASS。

Run: `cd backend && uv run pytest tests/test_real_stage_two.py -v -m real`

Expected: PASS，CLI 或测试输出至少出现一轮 `baseline≈... actual≈... gross saved≈... net saved≈...`。

- [ ] **Step 7: 手动运行用户的真实场景**

Run:

```bash
cd backend
uv run deeptrace "今天 AI 领域有哪些热点新闻？请自主搜索并抓取来源。"
```

Expected: 至少一次搜索和抓取；最终答案带成功来源；逐轮显示 Token 毛节省、压缩成本和净节省；没有整页正文出现在主 Agent 输入审计中。

- [ ] **Step 8: 提交阶段 2**

```bash
git add backend/src/deeptrace/agent.py backend/src/deeptrace/cli.py backend/README.md backend/tests/test_real_stage_two.py
git commit -m "feat: complete stage two research agent"
```

## Final Verification

- [ ] Run: `cd backend && uv run pytest -v -m "not real"`，Expected: PASS。
- [ ] Run: `cd backend && uv run pytest tests/test_real_stage_two.py -v -m real`，Expected: PASS。
- [ ] Run: `cd backend && uv run deeptrace "今年字节跳动 Agent 开发岗位有哪些招聘要求？"`，Expected: 搜索、抓取、笔记、来源和 Token 汇总均出现。
- [ ] Run: `git status --short`，Expected: 只保留用户原有的未提交改动，不出现 API Key、运行缓存或 Playwright 下载文件。
