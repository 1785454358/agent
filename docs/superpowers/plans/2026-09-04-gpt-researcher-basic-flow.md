# GPT-Researcher Basic Flow Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the task-level multi-round research loop with one initial search, one query-planning call, parallel search/scrape/context collection, and one Writer call.

**Architecture:** Keep the FastAPI, SSE, CLI, persistence, optional page memory, provider, scraper, usage accounting, and global budget shell. Replace `ResearchPlan → ResearchTask → ResearchNote → SectionResult` with `list[str] search_queries → dict[str, RawDocument] → research_context: str`; no evidence-like fragment object is stored or exposed.

**Tech Stack:** Python 3.12, asyncio, LangGraph, LangChain OpenAI, Tavily, local BGE-M3 runtime, FastAPI, Pydantic, pytest, uv.

**Spec:** `docs/superpowers/specs/2026-09-04-gpt-researcher-basic-flow-design.md`

## Global Constraints

- Only the default Basic research mode is implemented.
- The graph is exactly `START → plan → parallel_research → writer → END`.
- Default planning produces 3 generated queries and appends the original query after stable de-duplication.
- Search returns at most 5 results per query; scraping uses a shared concurrency limit of 15.
- Small contexts below 8000 characters skip embeddings; larger contexts use 1000-character chunks, 100-character overlap, a 0.42 similarity threshold, and at most 10 retained chunks per query.
- Runtime state and public APIs contain no `ResearchNote`, Evidence, Claim, Verifier, fragment ID, note ID, task loop, coverage loop, or compatibility shell for them.
- Writer input is one `Source / Title / Content` context string and Writer runs once, with one bounded retry before deterministic fallback.
- FastAPI, SSE, Web UI, CLI, run persistence, optional page memory, usage accounting, cancellation, and global limits remain functional.
- Existing user data under `backend/runs/`, `backend/memory/`, and `.env` must not be deleted or committed.

---

### Task 1: Replace the planner contract with a flat query list

**Files:**
- Modify: `backend/src/deeptrace/agent/planner.py`
- Modify: `backend/src/deeptrace/prompts/planner.py`
- Modify: `backend/tests/agent/test_planner.py`
- Delete: `backend/tests/models/test_plan.py`

**Interfaces:**
- Consumes: `question: str`, `initial_results: Sequence[Mapping[str, Any]]`.
- Produces: `parse_search_queries(raw: str) -> list[str]`.
- Produces: `PlannerAgent.aplan(question, initial_results) -> tuple[list[str], TokenUsage, bool, str]`.

- [ ] **Step 1: Replace planner tests with the flat-query behavior**

```python
def test_parse_search_queries_accepts_repaired_json() -> None:
    assert parse_search_queries('{"queries":["技术进展","商业动态"]}') == [
        "技术进展",
        "商业动态",
    ]


def test_planner_appends_original_query_once() -> None:
    model = ScriptedModel([AIMessage(content='["技术进展", "年度进展"]')])
    queries, _usage, fallback, error = asyncio.run(
        PlannerAgent(model, query_count=3).aplan(
            "年度进展",
            [{"title": "背景", "url": "https://example.com", "snippet": "摘要"}],
        )
    )
    assert queries == ["技术进展", "年度进展"]
    assert fallback is False
    assert error == ""


def test_planner_failure_falls_back_to_original_query() -> None:
    model = ScriptedModel([RuntimeError("provider down"), RuntimeError("provider down")])
    queries, _usage, fallback, error = asyncio.run(
        PlannerAgent(model, query_count=3, call_timeout_seconds=0.1).aplan("原始问题", [])
    )
    assert queries == ["原始问题"]
    assert fallback is True
    assert "provider down" in error
```

- [ ] **Step 2: Run the planner tests and verify RED**

Run: `cd backend && uv run pytest tests/agent/test_planner.py -v`

Expected: FAIL because the existing planner returns `ResearchPlan` and does not accept initial results.

- [ ] **Step 3: Implement the Basic planner**

Implement the prompt as one system message plus one JSON user payload containing `question`, `initial_results`, and `query_count`. Require either a JSON list or `{"queries": [...]}`. Normalize whitespace, discard empty/non-string entries, cap generated entries at `query_count`, append the normalized original question, and stable-deduplicate.

Use this constructor and call contract:

```python
class PlannerAgent:
    def __init__(
        self,
        model: Any,
        *,
        query_count: int = 3,
        call_timeout_seconds: float = 60.0,
    ) -> None: ...

    async def aplan(
        self,
        question: str,
        initial_results: Sequence[Mapping[str, Any]],
    ) -> tuple[list[str], TokenUsage, bool, str]: ...
```

Allow at most two model attempts under one absolute 60-second deadline. Return `[normalize_question(question)]` after timeout, provider failure, invalid JSON, or an empty list.

- [ ] **Step 4: Run planner tests and verify GREEN**

Run: `cd backend && uv run pytest tests/agent/test_planner.py -v`

Expected: PASS.

- [ ] **Step 5: Commit the planner contract**

```bash
git add backend/src/deeptrace/agent/planner.py backend/src/deeptrace/prompts/planner.py backend/tests/agent/test_planner.py backend/tests/models/test_plan.py
git commit -m "refactor: plan flat search queries"
```

### Task 2: Replace ResearchNote compression with direct context formatting

**Files:**
- Modify: `backend/src/deeptrace/context/compression.py`
- Modify: `backend/src/deeptrace/context/embeddings.py`
- Modify: `backend/src/deeptrace/context/__init__.py`
- Modify: `backend/tests/context/test_compression.py`
- Delete: `backend/src/deeptrace/context/chunking.py`
- Delete: `backend/src/deeptrace/context/retrieval.py`
- Delete: `backend/src/deeptrace/context/temporal.py`
- Delete: `backend/tests/context/test_retrieval.py`
- Delete: `backend/tests/context/test_temporal.py`

**Interfaces:**
- Consumes: `query: str`, `documents: Sequence[RawDocument]`.
- Produces: `format_document_context(document, content) -> str`.
- Produces: `ContextCompressor.aget_context(query, documents, max_results=10) -> str`.
- The function returns text only and never returns or stores a fragment object.

- [ ] **Step 1: Write direct-context tests**

```python
def test_small_context_skips_embedding(raw_document) -> None:
    runtime = SpyEmbeddingRuntime()
    compressor = ContextCompressor(runtime, direct_threshold_chars=8000)
    context = asyncio.run(compressor.aget_context("问题", [raw_document]))
    assert runtime.embed_calls == 0
    assert context == (
        "Source: https://example.com/a\n"
        "Title: 来源标题\n"
        "Content: 整页正文唯一标记\n"
    )


def test_large_context_filters_character_chunks(raw_document) -> None:
    document = raw_document.model_copy(update={"content": "相关内容" * 1500})
    compressor = ContextCompressor(
        DeterministicEmbeddingRuntime(),
        direct_threshold_chars=10,
        chunk_size=1000,
        chunk_overlap=100,
        similarity_threshold=0.42,
    )
    context = asyncio.run(compressor.aget_context("相关", [document], max_results=10))
    assert "Source: https://example.com/a" in context
    assert "Content:" in context
    assert len(context) < len(document.content) + 200
```

- [ ] **Step 2: Run compression tests and verify RED**

Run: `cd backend && uv run pytest tests/context/test_compression.py -v`

Expected: FAIL because `ContextCompressor` does not exist and compression returns `ResearchNote`.

- [ ] **Step 3: Implement character splitting and embedding filtering**

Implement private `_split_text(text, size=1000, overlap=100) -> list[str]` using character offsets only. For the small-content path, format up to `max_results` complete documents. For the large-content path, create transient `(document, text, order)` tuples, embed only their text, compare to `runtime.query_vector(query)`, retain scores `>= 0.42`, sort by descending score then original order, cap at 10, restore original order for prompt readability, and format directly. Simplify `CompressionRuntime` to text embedding and query-vector caching; remove `chunk_vectors` and `register_chunks`, which only support persisted `DocumentChunk` objects.

The output formatter must be exactly:

```python
def format_document_context(document: RawDocument, content: str) -> str:
    return (
        f"Source: {document.final_url}\n"
        f"Title: {document.title or document.final_url}\n"
        f"Content: {content.strip()}\n"
    )
```

- [ ] **Step 4: Run context tests and verify GREEN**

Run: `cd backend && uv run pytest tests/context/test_compression.py -v`

Expected: PASS.

- [ ] **Step 5: Commit direct context compression**

```bash
git add backend/src/deeptrace/context backend/tests/context
git commit -m "refactor: format research context directly"
```

### Task 3: Add one-pass parallel research collection

**Files:**
- Create: `backend/src/deeptrace/orchestration/research.py`
- Create: `backend/tests/orchestration/test_research.py`
- Modify: `backend/src/deeptrace/tools/search/tavily.py`
- Modify: `backend/src/deeptrace/orchestration/budget.py`
- Delete: `backend/src/deeptrace/orchestration/tool_executor.py`
- Delete: `backend/tests/orchestration/test_tool_executor.py`
- Delete: `backend/src/deeptrace/agent/researcher.py`
- Delete: `backend/src/deeptrace/prompts/researcher.py`
- Delete: `backend/tests/agent/test_researcher.py`

**Interfaces:**
- Produces internal operational `QueryResearchResult(query, context, sources, documents, candidate_count, fetch_success_count, fetch_failure_count, errors)`; this is not a persisted evidence/fragment model.
- Produces `ParallelResearchService.asearch_initial(question) -> dict[str, Any]`.
- Produces `ParallelResearchService.acollect(question, queries, initial_search) -> tuple[str, dict[str, RawDocument], list[str], list[QueryResearchResult]]`.

- [ ] **Step 1: Write concurrency and global URL de-duplication tests**

```python
def test_collect_runs_queries_concurrently() -> None:
    service = make_service(search_delay=0.05, queries={"a": ["https://e/a"], "b": ["https://e/b"]})
    started = time.perf_counter()
    context, documents, sources, results = asyncio.run(
        service.acollect("root", ["a", "b"], None)
    )
    assert time.perf_counter() - started < 0.09
    assert [item.query for item in results] == ["a", "b"]
    assert set(sources) == {"https://e/a", "https://e/b"}


def test_collect_fetches_duplicate_url_once() -> None:
    service, fetcher = make_counting_service(
        queries={"a": ["https://e/shared"], "b": ["https://e/shared"]}
    )
    asyncio.run(service.acollect("root", ["a", "b"], None))
    assert fetcher.calls == ["https://e/shared"]
```

- [ ] **Step 2: Run collection tests and verify RED**

Run: `cd backend && uv run pytest tests/orchestration/test_research.py -v`

Expected: FAIL because `ParallelResearchService` does not exist.

- [ ] **Step 3: Implement the collection fan-out/fan-in**

Implement this deterministic sequence:

```python
search_payloads = await asyncio.gather(
    *(search_one(query) for query in queries),
    return_exceptions=True,
)
url_jobs = claim_urls_in_query_order(search_payloads)
fetched = await asyncio.gather(
    *(fetch_with_semaphore(job) for job in url_jobs),
    return_exceptions=True,
)
contexts = await asyncio.gather(
    *(compressor.aget_context(query, documents_for_query) for query in queries)
)
```

Search uses `asyncio.to_thread(search_web, ...)`. URL claiming happens after all searches finish, in query/result order, so no shared-set race is possible. Fetching uses one `asyncio.Semaphore(settings.scraper_concurrency)`. Cache hits from page Memory and the in-run document map do not consume network page budget. Each query receives references to the globally fetched documents that appeared in its own result list, even when another query first claimed the URL.

Use `initial_search` for the original query instead of issuing that search twice. Preserve successful results when siblings fail.

- [ ] **Step 4: Run collection tests and verify GREEN**

Run: `cd backend && uv run pytest tests/orchestration/test_research.py -v`

Expected: PASS.

- [ ] **Step 5: Commit one-pass collection**

```bash
git add backend/src/deeptrace/orchestration/research.py backend/tests/orchestration/test_research.py backend/src/deeptrace/tools/search/tavily.py backend/src/deeptrace/orchestration/budget.py backend/src/deeptrace/orchestration/tool_executor.py backend/tests/orchestration/test_tool_executor.py backend/src/deeptrace/agent/researcher.py backend/src/deeptrace/prompts/researcher.py backend/tests/agent/test_researcher.py
git commit -m "refactor: collect research in one parallel pass"
```

### Task 4: Simplify Writer to consume one context string

**Files:**
- Modify: `backend/src/deeptrace/agent/writer.py`
- Modify: `backend/src/deeptrace/prompts/writer.py`
- Modify: `backend/tests/agent/test_writer.py`

**Interfaces:**
- Consumes: `question: str`, `context: str`, `sources: Sequence[str]`, `language: str`, `termination_reason: str`.
- Produces: `WriterOutcome(markdown: str, sources: list[str], usage: TokenUsage, used_fallback: bool)`.
- Produces: `WriterAgent.awrite(...) -> WriterOutcome`.

- [ ] **Step 1: Write string-context Writer tests**

```python
def test_writer_receives_source_title_content_context() -> None:
    model = CapturingModel("# 报告\n\n内容 ([来源](https://example.com/a))")
    outcome = asyncio.run(
        WriterAgent(model).awrite(
            question="研究问题",
            context="Source: https://example.com/a\nTitle: 标题\nContent: 原文\n",
            sources=["https://example.com/a"],
            language="zh-CN",
        )
    )
    assert "Source: https://example.com/a" in model.messages[-1].content
    assert not hasattr(outcome, "used_note_ids")


def test_writer_abstains_when_context_is_empty() -> None:
    outcome = asyncio.run(
        WriterAgent(FailingIfCalledModel()).awrite(
            question="研究问题", context="", sources=[], language="zh-CN"
        )
    )
    assert outcome.used_fallback is True
    assert "未获得有效资料" in outcome.markdown
```

- [ ] **Step 2: Run Writer tests and verify RED**

Run: `cd backend && uv run pytest tests/agent/test_writer.py -v`

Expected: FAIL because Writer requires plans, sections, and notes.

- [ ] **Step 3: Implement one-call report writing**

Build messages from a system prompt and a user message containing the question followed by the context string. Require inline Markdown hyperlinks whose URLs appear in the context. Do not parse note IDs, citation numbers, claims, or sections. Append a deterministic `## References` list containing unique `sources` after the model body.

Keep one shared deadline and at most two Provider attempts. The fallback report must include the question, a clear limitation, the available context truncated to the configured Writer context limit, and the same References list.

- [ ] **Step 4: Run Writer tests and verify GREEN**

Run: `cd backend && uv run pytest tests/agent/test_writer.py -v`

Expected: PASS.

- [ ] **Step 5: Commit the Writer simplification**

```bash
git add backend/src/deeptrace/agent/writer.py backend/src/deeptrace/prompts/writer.py backend/tests/agent/test_writer.py
git commit -m "refactor: write reports from flat context"
```

### Task 5: Reduce models and graph state to the Basic pipeline

**Files:**
- Modify: `backend/src/deeptrace/models/document.py`
- Modify: `backend/src/deeptrace/models/report.py`
- Modify: `backend/src/deeptrace/models/metrics.py`
- Modify: `backend/src/deeptrace/models/__init__.py`
- Modify: `backend/src/deeptrace/observability/token_metrics.py`
- Modify: `backend/src/deeptrace/observability/__init__.py`
- Modify: `backend/src/deeptrace/orchestration/state.py`
- Modify: `backend/src/deeptrace/orchestration/graph.py`
- Modify: `backend/tests/orchestration/test_state.py`
- Modify: `backend/tests/orchestration/test_graph.py`
- Modify: `backend/tests/test_module_layout.py`
- Modify: `backend/tests/observability/test_token_metrics.py`
- Delete: `backend/src/deeptrace/models/plan.py`
- Delete: `backend/src/deeptrace/models/research.py`
- Delete: `backend/src/deeptrace/models/quality.py`
- Delete: `backend/src/deeptrace/orchestration/coverage.py`
- Delete: `backend/src/deeptrace/orchestration/quality.py`
- Delete: `backend/tests/orchestration/test_coverage.py`
- Delete: `backend/tests/orchestration/test_note_quality.py`
- Delete: `backend/tests/models/test_quality.py`

**Interfaces:**
- Retains: `RawDocument`, `RunEvent`, `TokenUsage`, `UsageBreakdown`, `estimate_usage_cost`, and `format_role_usage`.
- `GraphState` contains `user_query`, `search_queries`, `initial_search`, `documents`, `research_context`, `final_sources`, events, status/budget/usage counters, and `final_answer`.

- [ ] **Step 1: Write state and graph contract tests**

```python
def test_graph_state_has_no_task_or_note_models() -> None:
    annotations = GraphState.__annotations__
    assert {"search_queries", "research_context", "final_sources"} <= annotations.keys()
    assert not ({"notes", "chunks", "research_plan", "task_coverages", "section_results", "used_note_ids"} & annotations.keys())


def test_graph_is_basic_pipeline() -> None:
    graph = build_research_graph()
    assert {"plan", "parallel_research", "writer"} <= set(graph.nodes)
    assert "research_all" not in graph.nodes
```

- [ ] **Step 2: Run state/graph tests and verify RED**

Run: `cd backend && uv run pytest tests/orchestration/test_state.py tests/orchestration/test_graph.py tests/test_module_layout.py -v`

Expected: FAIL because task, chunk, and note state still exists.

- [ ] **Step 3: Remove obsolete models and build the three-node graph**

Remove `RunEvent.task_id`; query identity belongs in `RunEvent.details["query"]`. Delete `ContextAudit`, `PageCompressionMetrics`, `RoundTokenMetrics`, `TokenEstimator`, `TokenLedger`, `calculate_round_metrics`, `format_round_metrics`, and `format_token_summary`. Reduce `UsageBreakdown` to `planner` and `writer`, because search, scraping, and local embeddings do not consume Provider tokens. Keep only `estimate_usage_cost` and a two-role `format_role_usage` in `observability/token_metrics.py`.

The graph wrapper names must be `_plan_node`, `_parallel_research_node`, and `_writer_node`; edges must exactly follow the spec.

- [ ] **Step 4: Run state/graph tests and verify GREEN**

Run: `cd backend && uv run pytest tests/orchestration/test_state.py tests/orchestration/test_graph.py tests/test_module_layout.py -v`

Expected: PASS.

- [ ] **Step 5: Commit model and graph reduction**

```bash
git add backend/src/deeptrace/models backend/src/deeptrace/orchestration backend/tests/models backend/tests/orchestration backend/tests/test_module_layout.py
git commit -m "refactor: reduce state to basic research flow"
```

### Task 6: Rebuild workflow nodes and the public agent service

**Files:**
- Replace: `backend/src/deeptrace/orchestration/nodes.py`
- Replace: `backend/src/deeptrace/agent/service.py`
- Modify: `backend/src/deeptrace/orchestration/__init__.py`
- Modify: `backend/src/deeptrace/agent/__init__.py`
- Modify: `backend/tests/orchestration/test_nodes.py`
- Modify: `backend/tests/agent/test_service.py`

**Interfaces:**
- `ResearchWorkflowNodes(plan_node, parallel_research_node, writer_node)` implements the three graph stages.
- `AgentResult` contains `status`, `answer`, `sources`, `steps`, `events`, `termination_reason`, `search_queries`, `provider_usage`, `role_usage`, `estimated_cost_usd`, and `stage_seconds`; it contains no round-token metric list.

- [ ] **Step 1: Write the three-node orchestration tests**

```python
def test_plan_node_searches_before_calling_planner() -> None:
    nodes, collector, planner = make_nodes()
    update = asyncio.run(nodes.plan_node(initial_state("问题")))
    assert collector.initial_search_calls == ["问题"]
    assert planner.initial_results == collector.initial_payload["results"]
    assert update["search_queries"][-1] == "问题"


def test_parallel_research_node_emits_query_events() -> None:
    nodes, _collector, _planner = make_nodes()
    update = asyncio.run(
        nodes.parallel_research_node({**initial_state("问题"), "search_queries": ["a", "b"]})
    )
    assert update["research_context"]
    assert [event.event_type for event in update["events"]].count("query.completed") == 2
    assert all(not event.event_type.startswith("task.") for event in update["events"])
```

- [ ] **Step 2: Run node/service tests and verify RED**

Run: `cd backend && uv run pytest tests/orchestration/test_nodes.py tests/agent/test_service.py -v`

Expected: FAIL because current nodes execute task loops and service returns plans, sections, and note IDs.

- [ ] **Step 3: Implement the nodes and service**

Replace `nodes.py` instead of editing both legacy and current classes. `plan_node` performs initial search, calls Planner once, records planner usage, and emits `planning.started`, `planning.completed`, and optional `planning.fallback`. `parallel_research_node` calls the collector once, emits one `query.started` and one `query.completed` event per query plus `research.completed`, and stores the flat context/documents/sources. `writer_node` calls Writer once and emits `writing.completed`, optional `writing.fallback`, and `run.completed`.

Replace `service.py` so it contains one `AgentResult`, one `ResearchAgent`, one `_initial_research_state`, and one `build_real_agent`; delete the duplicate legacy stage-2 definitions. Load Memory documents into the collector cache before graph invocation and write successful documents back afterward.

- [ ] **Step 4: Run node/service tests and verify GREEN**

Run: `cd backend && uv run pytest tests/orchestration/test_nodes.py tests/agent/test_service.py -v`

Expected: PASS.

- [ ] **Step 5: Commit orchestration and service**

```bash
git add backend/src/deeptrace/orchestration/nodes.py backend/src/deeptrace/orchestration/__init__.py backend/src/deeptrace/agent backend/tests/orchestration/test_nodes.py backend/tests/agent/test_service.py
git commit -m "refactor: run the basic research pipeline"
```

### Task 7: Align configuration, API, CLI, events, and documentation

**Files:**
- Modify: `backend/src/deeptrace/config/settings.py`
- Modify: `backend/.env.example`
- Modify: `backend/src/deeptrace/api.py`
- Modify: `backend/src/deeptrace/cli.py`
- Modify: `backend/bench_run.py`
- Modify: `backend/tests/config/test_settings.py`
- Modify: `backend/tests/api/test_api.py`
- Modify: `backend/tests/test_cli.py`
- Modify: `backend/README.md`
- Modify: `docs/q.md`

**Interfaces:**
- New settings: `search_query_count=3`, `max_search_results_per_query=5`, `scraper_concurrency=15`, `context_max_results=10`, `context_direct_threshold_chars=8000`, `context_chunk_chars=1000`, `context_chunk_overlap_chars=100`, `context_similarity_threshold=0.42`, `planner_timeout_seconds=60`, `writer_timeout_seconds=60`.
- Removed settings: task count, task concurrency, task rounds, minimum sources per task, query-loop threshold, and note/compression-only controls.
- API record replaces `plan` and `sections` with `search_queries`.

- [ ] **Step 1: Write configuration and API response tests**

```python
def test_basic_defaults() -> None:
    settings = settings_from_minimal_env()
    assert settings.search_query_count == 3
    assert settings.max_search_results_per_query == 5
    assert settings.scraper_concurrency == 15
    assert settings.context_similarity_threshold == 0.42
    assert not hasattr(settings, "max_task_rounds")


def test_run_record_exposes_queries_not_plan_or_sections() -> None:
    response = client.get(f"/researches/{run_id}").json()
    assert response["search_queries"] == ["技术进展", "原始问题"]
    assert "plan" not in response
    assert "sections" not in response
```

- [ ] **Step 2: Run config/API/CLI tests and verify RED**

Run: `cd backend && uv run pytest tests/config/test_settings.py tests/api/test_api.py tests/test_cli.py -v`

Expected: FAIL because the old task settings and response fields remain.

- [ ] **Step 3: Implement public-surface changes**

Read new environment variables using the existing bounded parsers. Set the default overall runtime to 300 seconds so stalled external services cannot recreate ten-minute runs. Update benchmark stages to planning, parallel research, and Writer only. Update frontend event rendering without adding a new UI mode selector.

Rewrite `backend/README.md` around the Basic pipeline, list only active environment variables, explain that `Content` is embedding-filtered source text rather than an LLM note, and remove all Claim/ResearchNote/task-round documentation. Append a dated entry to `docs/q.md` recording the architecture replacement and expected latency mechanism.

- [ ] **Step 4: Run public-surface tests and verify GREEN**

Run: `cd backend && uv run pytest tests/config/test_settings.py tests/api/test_api.py tests/test_cli.py -v`

Expected: PASS.

- [ ] **Step 5: Commit public surfaces**

```bash
git add backend/src/deeptrace/config/settings.py backend/.env.example backend/src/deeptrace/api.py backend/src/deeptrace/cli.py backend/bench_run.py backend/tests/config/test_settings.py backend/tests/api/test_api.py backend/tests/test_cli.py backend/README.md docs/q.md
git commit -m "docs: align the app with basic research mode"
```

### Task 8: Remove final obsolete exports and verify the complete refactor

**Files:**
- Delete: `backend/src/deeptrace/prompts/research.py`
- Modify: `backend/src/deeptrace/prompts/__init__.py`
- Modify: `backend/src/deeptrace/tools/__init__.py`
- Modify: `backend/src/deeptrace/__init__.py`
- Modify: `backend/tests/conftest.py`
- Do not modify: `backend/.env`, `backend/runs/`, `backend/memory/`.

**Interfaces:**
- The package imports successfully without any obsolete research domain object.
- All non-real tests pass and the default API completes one real research run within the 300-second global limit.

- [ ] **Step 1: Run obsolete-symbol scans**

Run:

```bash
rg -n "ResearchNote|CompressionOutcome|DocumentChunk|ResearchPlan|ResearchTask|TaskCoverage|TaskCompletion|SectionResult|used_note_ids|task_round|task_concurrency|Claim|Evidence|Verifier" backend/src backend/tests backend/README.md
```

Expected: no runtime or current-document matches. Historical terms may remain only in the dated problem log when explicitly marked as history.

- [ ] **Step 2: Remove the final obsolete prompt, tool schemas, fixtures, and exports**

Delete `prompts/research.py`, which only supports the removed tool-calling Agent loop. Reduce `prompts/__init__.py` to Planner and Writer exports. Reduce `tools/__init__.py` to `ToolContext` and `search_web`; delete `EXTERNAL_TOOL_SCHEMAS` and the `complete_research_task` schema. Remove task/note fixtures from `tests/conftest.py`, retaining only `raw_document`. Update the package root exports to expose `ResearchAgent`, `AgentResult`, `build_real_agent`, and active models only. Do not leave forwarding imports or compatibility aliases.

- [ ] **Step 3: Run the complete automated verification**

Run:

```bash
cd backend
uv lock --check
uv run pytest -m "not real"
uv run python -m compileall -q src tests
uv run deeptrace --help
```

Expected: every command exits 0 with no test failure or import error.

- [ ] **Step 4: Run repository checks**

Run:

```bash
git diff --check
git status --short
```

Expected: no whitespace errors and only intended refactor files are modified.

- [ ] **Step 5: Run one real API benchmark**

Start the API with the existing real `.env`, submit the same broad research question used in the previous benchmark, and verify:

```text
terminal status: completed or honest partial
events: planning.completed, query.completed, research.completed, writing.completed, run.completed
forbidden events: task.started, task.completed, tools.completed
report: non-empty
sources: non-empty
wall clock: less than 300 seconds
persisted run JSON: status, termination_reason, search_queries, usage, and events match the API
```

- [ ] **Step 6: Commit final cleanup**

```bash
git add backend docs
git commit -m "refactor: remove obsolete research layers"
```
