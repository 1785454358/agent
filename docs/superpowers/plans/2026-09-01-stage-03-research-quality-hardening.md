# Stage 3 Research Quality Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 加固阶段 3 的时间适配、来源选择、任务预算、中文写作和运行观测，使年度研究允许后发综述但不会把目标期外新事件写进报告。

**Architecture:** 保持现有 Planner → Researcher/Tools → Writer 六节点主图，在 RawDocument 与 ResearchNote 上增加来源时间和任务级事件时间元数据。搜索采用来源排序与每轮抓取上限，压缩负责隔离目标期内容，Coverage 只统计合格笔记；Graph State 增加按角色 Provider usage 和任务额度，Writer 只消费时间有效笔记并执行语言、时间表达校验。

**Tech Stack:** Python 3.12、Pydantic 2、LangChain、LangGraph、Tavily、HTTPX、BeautifulSoup、Trafilatura、SentenceTransformers/BGE-M3、pytest、uv。

**Spec:** `docs/superpowers/specs/2026-09-01-stage-03-research-quality-hardening-design.md`

## Global Constraints

- 代码只写入正式 `backend/`；保留必要中文注释和当前模块边界。
- 不新增 Claim、Evidence Store、Verifier、Memory、API、Web UI 或评测平台。
- 来源发布时间不得作为目标年份的硬删除条件；后发综述可以标记 `retrospective` 使用。
- `out_of_range` 不计入覆盖且不交给 Writer；`unknown` 不能成为关键结论唯一依据。
- 子任务继续串行执行；单轮抓取和压缩保持有界并发。
- 每个任务只运行列出的定向测试；最终运行现有非真实套件和一次真实外部冒烟。
- 真实验收必须使用真实 LLM、Tavily、网页抓取和 `D:\Dev\Models\bge-m3`，不得用 Fake 外部结果代替。
- 保留工作区现有无关修改、删除和未跟踪文件，只暂存本计划列出的文件。

---

### Task 1: 时间质量模型与确定性语言选择

**Files:**
- Create: `backend/src/deeptrace/models/quality.py`
- Modify: `backend/src/deeptrace/models/document.py`
- Modify: `backend/src/deeptrace/models/research.py`
- Modify: `backend/src/deeptrace/models/report.py`
- Modify: `backend/src/deeptrace/models/__init__.py`
- Modify: `backend/src/deeptrace/agent/planner.py`
- Modify: `backend/tests/conftest.py`
- Create: `backend/tests/models/test_quality.py`
- Modify: `backend/tests/agent/test_planner.py`

**Interfaces:**
- Consumes: `ResearchPlan.time_range`, `ResearchNote`, `TaskCoverage` and original question.
- Produces: `SourceKind`, `TemporalRelation`, `detect_query_language(question: str) -> str`, extended RawDocument/ResearchNote/TaskCoverage.

- [ ] **Step 1: Write failing tests**

```python
# tests/models/test_quality.py
def test_quality_defaults(raw_document, research_note, task_coverage):
    assert raw_document.source_published_at is None
    assert raw_document.source_modified_at is None
    assert raw_document.publisher is None
    assert research_note.source_kind == "unknown"
    assert research_note.temporal_relation == "not_applicable"
    assert research_note.event_start_date is None
    assert research_note.event_end_date is None
    assert task_coverage.valid_note_ids == []
    assert task_coverage.out_of_range_note_ids == []
    assert task_coverage.api_tokens_used == 0
```

```python
# tests/agent/test_planner.py
def test_query_language_is_deterministic():
    assert detect_query_language("2024年 AI Agent 有哪些进展？") == "zh-CN"
    assert detect_query_language("What changed in AI agents in 2024?") == "en"
```

- [ ] **Step 2: Verify RED**

Run: `uv run pytest tests/models/test_quality.py tests/agent/test_planner.py -v`

Expected: FAIL because the new types, fields and function are missing.

- [ ] **Step 3: Add types and backward-compatible fields**

```python
# src/deeptrace/models/quality.py
from typing import Literal

SourceKind = Literal["official", "academic", "reputable_secondary", "other", "unknown"]
TemporalRelation = Literal["in_range", "retrospective", "out_of_range", "unknown", "not_applicable"]
```

Add to RawDocument:

```python
source_published_at: datetime | None = None
source_modified_at: datetime | None = None
publisher: str | None = None
```

Add to ResearchNote:

```python
source_published_at: datetime | None = None
event_start_date: date | None = None
event_end_date: date | None = None
source_kind: SourceKind = "unknown"
temporal_relation: TemporalRelation = "not_applicable"
temporal_scope: str = ""
```

Add to TaskCoverage:

```python
valid_note_ids: list[str] = Field(default_factory=list)
retrospective_note_ids: list[str] = Field(default_factory=list)
unknown_time_note_ids: list[str] = Field(default_factory=list)
out_of_range_note_ids: list[str] = Field(default_factory=list)
qualified_source_urls: list[str] = Field(default_factory=list)
api_tokens_used: int = Field(default=0, ge=0)
api_token_budget: int = Field(default=0, ge=0)
```

Export both aliases from `models/__init__.py`.

- [ ] **Step 4: Make plan language deterministic**

```python
def detect_query_language(question: str) -> str:
    if re.search(rf"[{_CJK}]", question):
        return "zh-CN"
    if re.search(r"[A-Za-z]", question):
        return "en"
    return "zh-CN"
```

Use it in `materialize_plan` and `build_fallback_plan` instead of model language for Chinese/English input.

- [ ] **Step 5: Verify GREEN**

Run: `uv run pytest tests/models/test_quality.py tests/models/test_plan.py tests/agent/test_planner.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add backend/src/deeptrace/models/quality.py backend/src/deeptrace/models/document.py backend/src/deeptrace/models/research.py backend/src/deeptrace/models/report.py backend/src/deeptrace/models/__init__.py backend/src/deeptrace/agent/planner.py backend/tests/conftest.py backend/tests/models/test_quality.py backend/tests/agent/test_planner.py
git commit -m "feat: add research quality metadata"
```

### Task 2: HTML 来源元数据与安全 Token 计数

**Files:**
- Create: `backend/src/deeptrace/tools/scraper/metadata.py`
- Modify: `backend/src/deeptrace/tools/scraper/fetcher.py`
- Modify: `backend/src/deeptrace/tools/scraper/__init__.py`
- Modify: `backend/src/deeptrace/context/embeddings.py`
- Create: `backend/tests/tools/scraper/test_metadata.py`
- Modify: `backend/tests/tools/scraper/test_fetcher.py`
- Create: `backend/tests/context/test_embeddings.py`

**Interfaces:**
- Consumes: raw HTML inside AsyncWebFetcher.
- Produces: `SourceMetadata`, `extract_source_metadata(html: str) -> SourceMetadata`, populated RawDocument metadata and warning-free token counting.

- [ ] **Step 1: Write failing tests**

```python
def test_json_ld_metadata_has_priority():
    html = '<script type="application/ld+json">{"@type":"Article","datePublished":"2024-04-05T08:00:00Z","dateModified":"2024-04-06T09:00:00Z","publisher":{"name":"Example Lab"}}</script>'
    value = extract_source_metadata(html)
    assert value.published_at.isoformat() == "2024-04-05T08:00:00+00:00"
    assert value.modified_at.isoformat() == "2024-04-06T09:00:00+00:00"
    assert value.publisher == "Example Lab"


def test_missing_metadata_stays_none():
    value = extract_source_metadata("<body>2024 overview</body>")
    assert value.published_at is None
    assert value.publisher is None
```

Add one fetcher assertion for RawDocument metadata and one 9,000-token test asserting `count_tokens` does not truncate or emit a transformers max-length warning.

- [ ] **Step 2: Verify RED**

Run: `uv run pytest tests/tools/scraper/test_metadata.py tests/tools/scraper/test_fetcher.py tests/context/test_embeddings.py -v`

Expected: FAIL because extraction and propagation are absent.

- [ ] **Step 3: Implement deterministic extraction**

```python
@dataclass(frozen=True, slots=True)
class SourceMetadata:
    published_at: datetime | None = None
    modified_at: datetime | None = None
    publisher: str | None = None


def extract_source_metadata(html: str) -> SourceMetadata:
    """优先 JSON-LD，再读取 article/meta/time；失败字段保持 None。"""
```

Parse JSON-LD objects/arrays first, then `article:published_time`, `article:modified_time`, `datePublished`, `dateModified`, `date`, and `<time datetime>`. Accept ISO-8601 only. Never infer publication time from crawl time or arbitrary body years.

Extend ExtractionCandidate with metadata fields, populate them in `_extract_candidates`, and copy the selected values into RawDocument.

- [ ] **Step 4: Remove false tokenizer warning without truncation**

Use the fast tokenizer with `verbose=False`, `truncation=False`, `return_length=True`; return its length and assert it remains greater than 8,192 in the long-input test.

- [ ] **Step 5: Verify GREEN**

Run: `uv run pytest tests/tools/scraper/test_metadata.py tests/tools/scraper/test_fetcher.py tests/context/test_embeddings.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add backend/src/deeptrace/tools/scraper/metadata.py backend/src/deeptrace/tools/scraper/fetcher.py backend/src/deeptrace/tools/scraper/__init__.py backend/src/deeptrace/context/embeddings.py backend/tests/tools/scraper/test_metadata.py backend/tests/tools/scraper/test_fetcher.py backend/tests/context/test_embeddings.py
git commit -m "feat: extract source publication metadata"
```

### Task 3: 来源候选排序与渐进式抓取上限

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `backend/uv.lock`
- Create: `backend/src/deeptrace/tools/search/ranking.py`
- Modify: `backend/src/deeptrace/tools/search/tavily.py`
- Modify: `backend/src/deeptrace/tools/search/__init__.py`
- Modify: `backend/src/deeptrace/tools/__init__.py`
- Modify: `backend/src/deeptrace/prompts/researcher.py`
- Modify: `backend/src/deeptrace/orchestration/tool_executor.py`
- Create: `backend/tests/tools/search/test_ranking.py`
- Modify: `backend/tests/orchestration/test_tool_executor.py`
- Modify: `backend/tests/test_module_layout.py`

**Interfaces:**
- Consumes: Tavily result dictionaries, target years and a batch of model tool calls.
- Produces: `rank_search_results(results, query, target_years)`, up to eight ordered candidates and no more than three actual fetches per tools node.

- [ ] **Step 1: Write failing tests**

```python
def test_ranking_prefers_primary_and_diverse_sources():
    results = [
        {"title": "Best agents in 2026", "url": "https://seo.example/list", "snippet": "2026"},
        {"title": "2024 agent release", "url": "https://openai.com/research/release", "snippet": "2024 release"},
        {"title": "2024 agent paper", "url": "https://arxiv.org/abs/2401.00001", "snippet": "2024"},
    ]
    ranked = rank_search_results(results, "2024 agent progress", {2024})
    assert [item["url"] for item in ranked[:2]] == [
        "https://openai.com/research/release",
        "https://arxiv.org/abs/2401.00001",
    ]
```

In tool-executor tests send five fetch calls, assert the fetcher sees only three, and assert all five tool_call_ids receive ToolMessages; deferred calls use `deferred_batch_limit`.

- [ ] **Step 2: Verify RED**

Run: `uv run pytest tests/tools/search/test_ranking.py tests/orchestration/test_tool_executor.py tests/test_module_layout.py -v`

Expected: FAIL because ranking and the batch limit do not exist.

- [ ] **Step 3: Add registered-domain dependency and ranking**

Add `"tld>=0.13"` to dependencies and run `uv lock`. Use `tld.get_fld(url, fail_silently=True)` rather than handwritten public-suffix rules.

```python
def rank_search_results(
    results: Sequence[dict[str, Any]],
    query: str,
    target_years: set[int],
) -> list[dict[str, Any]]:
    """按相关度、目标年份、一手特征和域名多样性稳定排序。"""
```

Retain original fields, add `registered_domain` and `source_priority`, demote Top/Best/榜单 and non-target-only years, and interleave registered domains before selecting another result from the same domain.

- [ ] **Step 4: Expand search and cap each fetch batch**

Raise the search schema and `search_web` limit from 5 to 8. Rank results before returning them; derive target years from `state["research_plan"].time_range`.

Accept only the first three fetch calls in `aexecute`. Return `deferred_batch_limit` for every remaining fetch call so tool-call mapping is complete. Update the Researcher prompt with contemporary-primary, retrospective and gap-filling query intents plus the three-fetch limit.

- [ ] **Step 5: Verify GREEN**

Run: `uv run pytest tests/tools/search/test_ranking.py tests/orchestration/test_tool_executor.py tests/test_module_layout.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add backend/pyproject.toml backend/uv.lock backend/src/deeptrace/tools/search/ranking.py backend/src/deeptrace/tools/search/tavily.py backend/src/deeptrace/tools/search/__init__.py backend/src/deeptrace/tools/__init__.py backend/src/deeptrace/prompts/researcher.py backend/src/deeptrace/orchestration/tool_executor.py backend/tests/tools/search/test_ranking.py backend/tests/orchestration/test_tool_executor.py backend/tests/test_module_layout.py
git commit -m "feat: rank and bound research candidates"
```

### Task 4: 时间感知 ResearchNote 压缩

**Files:**
- Create: `backend/src/deeptrace/context/temporal.py`
- Modify: `backend/src/deeptrace/context/compression.py`
- Modify: `backend/src/deeptrace/context/__init__.py`
- Modify: `backend/src/deeptrace/prompts/compression.py`
- Modify: `backend/src/deeptrace/orchestration/tool_executor.py`
- Create: `backend/tests/context/test_temporal.py`
- Modify: `backend/tests/context/test_compression.py`

**Interfaces:**
- Consumes: `ResearchTimeRange | None`, RawDocument source metadata, selected chunks and model-returned event dates.
- Produces: `normalize_temporal_relation(time_range, source_published_at, event_start_date, event_end_date) -> TemporalRelation`, extended ResearchNotePayload and time-qualified ResearchNotes.

- [ ] **Step 1: Write failing tests**

```python
RANGE_2024 = ResearchTimeRange(
    start_date=date(2024, 1, 1), end_date=date(2024, 12, 31), description="2024"
)


def test_later_review_of_2024_is_retrospective():
    assert normalize_temporal_relation(
        RANGE_2024,
        datetime(2026, 2, 1, tzinfo=UTC),
        date(2024, 3, 1),
        date(2024, 3, 1),
    ) == "retrospective"


def test_later_event_is_out_of_range():
    assert normalize_temporal_relation(
        RANGE_2024,
        datetime(2026, 2, 1, tzinfo=UTC),
        date(2026, 1, 1),
        date(2026, 1, 1),
    ) == "out_of_range"


def test_untimed_question_is_not_applicable():
    assert normalize_temporal_relation(None, None, None, None) == "not_applicable"
```

Add compression tests for event-date parsing, retrospective/out-of-range notes, and timed extractive fallback becoming `unknown`.

- [ ] **Step 2: Verify RED**

Run: `uv run pytest tests/context/test_temporal.py tests/context/test_compression.py -v`

Expected: FAIL because normalization and payload fields are missing.

- [ ] **Step 3: Implement deterministic normalization**

```python
def normalize_temporal_relation(time_range, source_published_at, event_start_date, event_end_date):
    if time_range is None:
        return "not_applicable"
    if not time_range.start_date or not time_range.end_date:
        return "unknown"
    if event_start_date is None or event_end_date is None:
        return "unknown"
    if event_start_date > event_end_date:
        raise ValueError("事件起始日期不能晚于结束日期")
    if event_end_date < time_range.start_date or event_start_date > time_range.end_date:
        return "out_of_range"
    if source_published_at and source_published_at.date() > time_range.end_date:
        return "retrospective"
    return "in_range"
```

- [ ] **Step 4: Extend compression request, prompt and payload**

Add `time_range: ResearchTimeRange | None` to CompressionRequest. Add to ResearchNotePayload:

```python
event_start_date: date | None = None
event_end_date: date | None = None
source_kind: SourceKind = "unknown"
temporal_scope: str = ""
```

The prompt receives target range, source publication metadata and publisher. It must remove out-of-range key points and return every field above. Always derive temporal_relation locally. Timed extractive fallback is `unknown`; untimed fallback is `not_applicable`.

- [ ] **Step 5: Pass plan range and count only useful notes**

Read the current plan range when constructing CompressionRequest. A new note is useful only when not irrelevant and not out_of_range; out-of-range results remain available for diagnostics.

- [ ] **Step 6: Verify GREEN**

Run: `uv run pytest tests/context/test_temporal.py tests/context/test_compression.py tests/orchestration/test_tool_executor.py -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add backend/src/deeptrace/context/temporal.py backend/src/deeptrace/context/compression.py backend/src/deeptrace/context/__init__.py backend/src/deeptrace/prompts/compression.py backend/src/deeptrace/orchestration/tool_executor.py backend/tests/context/test_temporal.py backend/tests/context/test_compression.py backend/tests/orchestration/test_tool_executor.py
git commit -m "feat: qualify notes by research time range"
```

### Task 5: 来源质量与覆盖状态

**Files:**
- Create: `backend/src/deeptrace/orchestration/quality.py`
- Modify: `backend/src/deeptrace/orchestration/coverage.py`
- Modify: `backend/src/deeptrace/orchestration/tool_executor.py`
- Modify: `backend/src/deeptrace/orchestration/nodes.py`
- Modify: `backend/src/deeptrace/orchestration/__init__.py`
- Create: `backend/tests/orchestration/test_quality.py`
- Modify: `backend/tests/orchestration/test_coverage.py`
- Modify: `backend/tests/orchestration/test_tool_executor.py`
- Modify: `backend/tests/orchestration/test_nodes.py`

**Interfaces:**
- Consumes: time-qualified ResearchNotes and source URLs.
- Produces: `note_is_valid`, `source_identity`, `summarize_note_quality`, quality buckets and SectionResult IDs excluding out-of-range notes.

- [ ] **Step 1: Write failing tests**

```python
def test_retrospective_counts_but_out_of_range_does_not(
    research_task, task_coverage, task_completion, research_note
):
    review = research_note.model_copy(update={
        "note_id": "note-review", "source_url": "https://openai.com/review",
        "source_kind": "official", "temporal_relation": "retrospective",
    })
    later = research_note.model_copy(update={
        "note_id": "note-later", "source_url": "https://example.org/later",
        "source_kind": "reputable_secondary", "temporal_relation": "out_of_range",
    })
    result = complete_coverage(
        research_task, task_coverage, task_completion, [review, later], []
    )
    assert result.valid_note_ids == ["note-review"]
    assert result.out_of_range_note_ids == ["note-later"]
    assert "https://example.org/later" not in result.qualified_source_urls
```

Add tests that two URLs on one registered domain do not satisfy diversity and only other/unknown source kinds cannot reach sufficient.

- [ ] **Step 2: Verify RED**

Run: `uv run pytest tests/orchestration/test_quality.py tests/orchestration/test_coverage.py -v`

Expected: FAIL because quality bucketing is absent.

- [ ] **Step 3: Implement quality helpers**

```python
QUALIFIED_SOURCE_KINDS = {"official", "academic", "reputable_secondary"}


def note_is_valid(note: ResearchNote) -> bool:
    if note.compression_status == "irrelevant":
        return False
    return note.temporal_relation in {"in_range", "retrospective", "not_applicable"}


def source_identity(url: str) -> str:
    return get_fld(url, fail_silently=True) or (urlsplit(url).hostname or url)
```

`summarize_note_quality` returns ordered note buckets, qualified URLs and unique source identities without mutation.

- [ ] **Step 4: Make coverage and tools node quality-aware**

Populate every new TaskCoverage bucket. Sufficient requires min_sources, at least two source identities, at least one valid qualified source kind and no unresolved topics. Preserve relevant_note_ids for diagnostics, but build SectionResult.note_ids from valid_note_ids.

Set consecutive_empty_rounds from valid new-note count. Tool events report in_range, retrospective, unknown and out_of_range counts.

- [ ] **Step 5: Verify GREEN**

Run: `uv run pytest tests/orchestration/test_quality.py tests/orchestration/test_coverage.py tests/orchestration/test_tool_executor.py tests/orchestration/test_nodes.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add backend/src/deeptrace/orchestration/quality.py backend/src/deeptrace/orchestration/coverage.py backend/src/deeptrace/orchestration/tool_executor.py backend/src/deeptrace/orchestration/nodes.py backend/src/deeptrace/orchestration/__init__.py backend/tests/orchestration/test_quality.py backend/tests/orchestration/test_coverage.py backend/tests/orchestration/test_tool_executor.py backend/tests/orchestration/test_nodes.py
git commit -m "feat: enforce qualified research coverage"
```

### Task 6: 公平任务预算与按角色 Provider Usage

**Files:**
- Modify: `backend/src/deeptrace/config/settings.py`
- Modify: `backend/.env.example`
- Modify: `backend/src/deeptrace/models/metrics.py`
- Modify: `backend/src/deeptrace/models/__init__.py`
- Modify: `backend/src/deeptrace/orchestration/state.py`
- Modify: `backend/src/deeptrace/orchestration/budget.py`
- Modify: `backend/src/deeptrace/orchestration/tool_executor.py`
- Modify: `backend/src/deeptrace/orchestration/nodes.py`
- Modify: `backend/src/deeptrace/agent/service.py`
- Modify: `backend/tests/config/test_settings.py`
- Modify: `backend/tests/orchestration/test_state.py`
- Create: `backend/tests/orchestration/test_budget.py`
- Modify: `backend/tests/orchestration/test_nodes.py`
- Modify: `backend/tests/agent/test_service.py`

**Interfaces:**
- Consumes: total usage, current task usage, remaining tasks and max_api_tokens.
- Produces: `UsageBreakdown`, `merge_usage_breakdown`, `writer_token_reserve`, `task_token_allowance`, `task_budget_reason` and AgentResult role usage.

- [ ] **Step 1: Write failing tests**

```python
def test_task_allowance_preserves_writer_and_remaining_tasks(settings, research_plan):
    state = {
        "api_token_count": 10_000,
        "current_task_index": 0,
        "research_plan": research_plan,
        "task_coverages": {},
    }
    assert writer_token_reserve(settings) == 18_000
    assert task_token_allowance(state, settings) == 46_000


def test_usage_breakdown_reducer_adds_roles():
    left = UsageBreakdown(planner=TokenUsage(total_tokens=10))
    right = UsageBreakdown(compression=TokenUsage(total_tokens=20))
    merged = merge_usage_breakdown(left, right)
    assert merged.planner.total_tokens == 10
    assert merged.compression.total_tokens == 20
    assert merged.total.total_tokens == 30
```

The 46,000 example is `(120000 - 18000 - 10000) / 2`.

- [ ] **Step 2: Verify RED**

Run: `uv run pytest tests/orchestration/test_budget.py tests/orchestration/test_state.py tests/config/test_settings.py -v`

Expected: FAIL because reserve, allowance and role usage are missing.

- [ ] **Step 3: Add config and UsageBreakdown**

Add `writer_token_reserve_ratio: float = 0.15`, read `DEEPTRACE_WRITER_TOKEN_RESERVE_RATIO` with bounds 0.05–0.40, and add it to `.env.example`.

```python
class UsageBreakdown(BaseModel):
    planner: TokenUsage = Field(default_factory=TokenUsage)
    researcher: TokenUsage = Field(default_factory=TokenUsage)
    compression: TokenUsage = Field(default_factory=TokenUsage)
    writer: TokenUsage = Field(default_factory=TokenUsage)

    @property
    def total(self) -> TokenUsage:
        return add_token_usages(
            self.planner, self.researcher, self.compression, self.writer
        )
```

Implement the helpers without mutation:

```python
def add_token_usages(*items: TokenUsage) -> TokenUsage:
    return TokenUsage(
        input_tokens=sum(item.input_tokens for item in items),
        output_tokens=sum(item.output_tokens for item in items),
        total_tokens=sum(item.total_tokens for item in items),
    )


def merge_usage_breakdown(left: UsageBreakdown, right: UsageBreakdown) -> UsageBreakdown:
    return UsageBreakdown(
        planner=add_token_usages(left.planner, right.planner),
        researcher=add_token_usages(left.researcher, right.researcher),
        compression=add_token_usages(left.compression, right.compression),
        writer=add_token_usages(left.writer, right.writer),
    )
```

Add `role_usage: Annotated[UsageBreakdown, merge_usage_breakdown]` to GraphState and initialize it in ResearchAgent.arun.

- [ ] **Step 4: Implement reserve and task allowance**

```python
def writer_token_reserve(settings: Settings) -> int:
    return int(settings.max_api_tokens * settings.writer_token_reserve_ratio)


def task_token_allowance(state: GraphState, settings: Settings) -> int:
    plan = state["research_plan"]
    remaining = max(1, len(plan.tasks) - state.get("current_task_index", 0))
    pool = max(0, settings.max_api_tokens - writer_token_reserve(settings) - state.get("api_token_count", 0))
    return pool // remaining
```

At start_task_node store allowance in `TaskCoverage.api_token_budget`. Increment api_tokens_used in research and tools nodes. Before another call, stop the current task with `task_token_budget` when used >= allowance.

```python
def task_budget_reason(coverage: TaskCoverage) -> str | None:
    if coverage.api_token_budget and coverage.api_tokens_used >= coverage.api_token_budget:
        return "task_token_budget"
    return None
```

Before compress_many, estimate each request prompt with TokenEstimator and keep the largest leading subset within the task remainder. Return `deferred_token_budget` ToolMessages for skipped calls.

- [ ] **Step 5: Tag usage at role boundaries**

Change `_usage_update` to accept planner/researcher/writer role and emit one-role UsageBreakdown deltas. ToolExecutionUpdate emits compression usage. AgentResult returns role_usage; tests require `role_usage.total == provider_usage`.

- [ ] **Step 6: Verify GREEN**

Run: `uv run pytest tests/orchestration/test_budget.py tests/orchestration/test_state.py tests/orchestration/test_nodes.py tests/agent/test_service.py tests/config/test_settings.py -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add backend/src/deeptrace/config/settings.py backend/.env.example backend/src/deeptrace/models/metrics.py backend/src/deeptrace/models/__init__.py backend/src/deeptrace/orchestration/state.py backend/src/deeptrace/orchestration/budget.py backend/src/deeptrace/orchestration/tool_executor.py backend/src/deeptrace/orchestration/nodes.py backend/src/deeptrace/agent/service.py backend/tests/config/test_settings.py backend/tests/orchestration/test_state.py backend/tests/orchestration/test_budget.py backend/tests/orchestration/test_nodes.py backend/tests/agent/test_service.py
git commit -m "feat: allocate fair research token budgets"
```

### Task 7: Writer 质量门与可解释 CLI

**Files:**
- Modify: `backend/src/deeptrace/prompts/writer.py`
- Modify: `backend/src/deeptrace/agent/writer.py`
- Modify: `backend/src/deeptrace/orchestration/tool_executor.py`
- Modify: `backend/src/deeptrace/orchestration/nodes.py`
- Modify: `backend/src/deeptrace/observability/token_metrics.py`
- Modify: `backend/src/deeptrace/observability/__init__.py`
- Modify: `backend/src/deeptrace/cli.py`
- Modify: `backend/tests/agent/test_writer.py`
- Modify: `backend/tests/orchestration/test_nodes.py`
- Modify: `backend/tests/observability/test_token_metrics.py`
- Modify: `backend/tests/test_cli.py`

**Interfaces:**
- Consumes: language-fixed plan, qualified notes, execution counters and UsageBreakdown.
- Produces: `is_language_consistent`, `find_unqualified_year_mentions`, one corrective Writer retry, detailed tool events and role Token summary.

- [ ] **Step 1: Write failing tests**

```python
def test_chinese_plan_rejects_english_report():
    assert not is_language_consistent("Only English text about agents.", "zh-CN")
    assert is_language_consistent("这是关于智能体的中文报告。", "zh-CN")


def test_unqualified_later_year_is_flagged():
    assert find_unqualified_year_mentions(
        "OpenAI Presence 于 2026 年发布。", 2024, 2024
    ) == [2026]
    assert find_unqualified_year_mentions(
        "后续回顾：Presence 于 2026 年发布，不属于 2024 年进展。", 2024, 2024
    ) == []
```

Add an async test where the first response is English and the second Chinese; assert exactly two calls and no fallback. Add a no-valid-notes test requiring deterministic refusal of factual conclusions.

- [ ] **Step 2: Verify RED**

Run: `uv run pytest tests/agent/test_writer.py tests/observability/test_token_metrics.py tests/test_cli.py -v`

Expected: FAIL because validators and role summary are missing.

- [ ] **Step 3: Implement prompt and validators**

Serialize source publication time, event dates, source_kind, temporal_relation and temporal_scope. Require plan.language, target range, retrospective wording and grouped sources.

```python
def is_language_consistent(markdown: str, language: str) -> bool:
    cjk = len(re.findall(r"[\u3400-\u9fff]", markdown))
    latin = len(re.findall(r"[A-Za-z]", markdown))
    return cjk >= max(8, latin // 5) if language == "zh-CN" else latin >= max(8, cjk)


def find_unqualified_year_mentions(markdown: str, start_year: int, end_year: int) -> list[int]:
    """标记未带后续、回顾、截至、不属于等说明的越界年份。"""
```

Split Markdown into sentences, ignore source-list URLs, and treat an out-of-range year as qualified only when the same sentence contains one of `后续`, `回顾`, `截至`, `后来`, `不属于`, `retrospective`, `subsequent`, `as of`, or `outside the period`.

On the second attempt append a HumanMessage with exact violations. Never retry more than once. If no qualified notes exist, bypass the model and return the deterministic limited report.

- [ ] **Step 4: Add execution statistics**

Extend ToolExecutionUpdate with candidate/fetch/skip counts, temporal counts and `error_counts: dict[str, int]`. Populate them at search, fetch and compression boundaries. The tools-node event includes counts and aggregated failure codes.

- [ ] **Step 5: Format role usage**

```python
def format_role_usage(usage: UsageBreakdown) -> str:
    return (
        "Provider Token（按角色）\n"
        f"Planner: {usage.planner.total_tokens:,}\n"
        f"Researcher: {usage.researcher.total_tokens:,}\n"
        f"Compression: {usage.compression.total_tokens:,}\n"
        f"Writer: {usage.writer.total_tokens:,}\n"
        f"Total: {usage.total.total_tokens:,}"
    )
```

Keep context savings separate. Remove the misleading stage-2-only main-agent usage line; print authoritative role usage from AgentResult.

- [ ] **Step 6: Verify GREEN**

Run: `uv run pytest tests/agent/test_writer.py tests/orchestration/test_nodes.py tests/observability/test_token_metrics.py tests/test_cli.py -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add backend/src/deeptrace/prompts/writer.py backend/src/deeptrace/agent/writer.py backend/src/deeptrace/orchestration/tool_executor.py backend/src/deeptrace/orchestration/nodes.py backend/src/deeptrace/observability/token_metrics.py backend/src/deeptrace/observability/__init__.py backend/src/deeptrace/cli.py backend/tests/agent/test_writer.py backend/tests/orchestration/test_nodes.py backend/tests/observability/test_token_metrics.py backend/tests/test_cli.py
git commit -m "feat: enforce report quality gates"
```

### Task 8: Integration, documentation and real acceptance

**Files:**
- Modify: `backend/README.md`
- Modify: `docs/README.md`
- Modify: `docs/superpowers/specs/2026-09-01-stage-03-research-quality-hardening-design.md`
- Test: existing `backend/tests/`

**Interfaces:**
- Consumes: Tasks 1–7 and real `.env` configuration.
- Produces: integrated quality-hardened CLI, updated docs and one real smoke record; no stage 4 code.

- [ ] **Step 1: Run focused integration tests**

```powershell
uv run pytest tests/models/test_quality.py tests/tools/scraper/test_metadata.py tests/tools/search/test_ranking.py tests/context/test_temporal.py tests/context/test_compression.py tests/orchestration/test_quality.py tests/orchestration/test_coverage.py tests/orchestration/test_budget.py tests/orchestration/test_nodes.py tests/agent/test_writer.py tests/test_cli.py -v
```

Expected: PASS.

- [ ] **Step 2: Run suite and compile check**

```powershell
uv run pytest -m "not real"
uv run python -m compileall src tests
```

Expected: all tests PASS and compileall exits 0.

- [ ] **Step 3: Run one real smoke**

```powershell
$env:DEEPTRACE_ALLOW_BENCHMARK_DNS_PROXY='true'
$env:PYTHONUNBUFFERED='1'
uv run deeptrace "2024年AI Agent领域有哪些重要进展？"
```

Acceptance evidence:

- at least two tasks obtain real valid notes;
- later reviews are allowed and visibly retrospective;
- Presence, Microsoft Agent Framework, HubSpot Spring 2025 and other later events are not presented as 2024 progress;
- at least one section uses official, academic or reputable secondary material;
- report language is Chinese;
- every task gets one research opportunity while budget remains;
- partial state and stop reasons are honest;
- CLI prints fetch/time-filter counts and role usage;
- no unhandled exception and no Fake external result.

If one real provider/site fails, preserve its code and retry only the affected smoke once. Never replace it with static data.

- [ ] **Step 4: Update docs from actual behavior**

Document dual time, source kinds, three-fetch cap, writer reserve ratio, role usage and run commands in backend README. Mark the hardening spec completed and link spec/plan from docs README; stage 4 remains next.

- [ ] **Step 5: Check secrets and scope**

```powershell
git status --short
git diff --check
git diff --name-only
git grep -n -I -E "sk-[A-Za-z0-9_-]{12,}|TAVILY_API_KEY=.*[^=[:space:]]" -- . ":(exclude)backend/.env" ":(exclude)docs/superpowers/plans/2026-09-01-stage-03-research-quality-hardening.md"
```

Expected: no secret values; existing unrelated dirty files remain unchanged.

- [ ] **Step 6: Commit**

```powershell
git add backend/README.md docs/README.md docs/superpowers/specs/2026-09-01-stage-03-research-quality-hardening-design.md
git commit -m "docs: complete stage 3 quality hardening"
```

## Final Acceptance

- [ ] Publication time and event time are distinct.
- [ ] Later retrospective sources can contribute target-period material.
- [ ] Later events cannot count toward coverage or Writer input.
- [ ] Sufficient coverage requires time fit, source diversity and one qualified source kind.
- [ ] Search candidates are ranked and each tools round fetches at most three pages.
- [ ] Tasks receive fair allowances and Writer tokens are reserved.
- [ ] Chinese questions produce Chinese reports or Chinese fallback.
- [ ] Writer retries once for language or unqualified year expressions.
- [ ] CLI explains candidate, fetch, filter and compression outcomes.
- [ ] Provider usage is consistent by role and total.
- [ ] Existing compression, scraper fallback and tool-call mapping still work.
- [ ] Automated tests and one real API smoke pass without Fake external results.
- [ ] No stage 4–6 modules or empty directories are added.
