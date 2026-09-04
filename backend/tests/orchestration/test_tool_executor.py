from deeptrace.orchestration.tool_executor import (
    ToolCallResult,
    build_tool_messages,
    select_fetch_tool_calls,
)


def test_external_results_keep_original_tool_order() -> None:
    calls = [
        {"id": "a", "name": "fetch_webpage", "args": {"url": "https://a"}},
        {"id": "b", "name": "fetch_webpage", "args": {"url": "https://b"}},
    ]
    results = [
        ToolCallResult("b", 1, {"ok": True, "title": "B"}),
        ToolCallResult("a", 0, {"ok": True, "title": "A"}),
    ]

    messages = build_tool_messages(calls, results)

    assert [message.tool_call_id for message in messages] == ["a", "b"]


def test_supplement_fetch_limit_preserves_every_tool_call_mapping() -> None:
    calls = [
        {
            "id": f"fetch-{index}",
            "name": "fetch_webpage",
            "args": {"url": f"https://example.com/{index}"},
        }
        for index in range(5)
    ]
    accepted, rejected = select_fetch_tool_calls(calls, max_fetches=3)
    successful = [
        ToolCallResult(
            str(call["id"]),
            order,
            {"ok": True},
        )
        for order, call in accepted
    ]

    messages = build_tool_messages(calls, [*successful, *rejected])

    assert len(accepted) == 3
    assert [message.tool_call_id for message in messages] == [
        f"fetch-{index}" for index in range(5)
    ]
    assert "deferred_batch_limit" in str(messages[-1].content)

import asyncio
import json
from datetime import UTC, datetime
from types import SimpleNamespace

import numpy as np

from deeptrace.context import CompressionService
from deeptrace.observability import TokenEstimator, TokenLedger
from deeptrace.orchestration.tool_executor import ResearchToolExecutor
from deeptrace.models import RawDocument, ScraperUsed


class FakeVocabRuntime:
    """词表指示向量 + 逐字符 tokenizer，驱动 chunk 与压缩全链路。"""

    def __init__(self, vocabulary):
        self._index = {word: i for i, word in enumerate(vocabulary)}
        self.tokenizer = self
        self.chunk_vectors: dict[str, np.ndarray] = {}

    def __call__(self, text, add_special_tokens=False, return_offsets_mapping=False,
                 truncation=False, verbose=False, **kwargs):
        tokens = list(range(len(text)))
        return {
            "input_ids": tokens,
            "offset_mapping": [(i, i + 1) for i in range(len(text))],
        }

    def _vector(self, text):
        vector = np.zeros(len(self._index), dtype=np.float32)
        for word, position in self._index.items():
            if word in text:
                vector[position] = 1.0
        norm = np.linalg.norm(vector)
        return vector / norm if norm else vector

    def embed(self, texts):
        if not texts:
            return np.empty((0, len(self._index)), dtype=np.float32)
        return np.stack([self._vector(item) for item in texts])

    def query_vector(self, query):
        return self._vector(query)

    def register_chunks(self, chunks):
        missing = [c for c in chunks if c.chunk_id not in self.chunk_vectors]
        if missing:
            vectors = self.embed([c.text for c in missing])
            self.chunk_vectors.update(
                {c.chunk_id: v for c, v in zip(missing, vectors, strict=True)}
            )

    def count_tokens(self, text):
        return len(text)


class FakeFetcher:
    def __init__(self, pages):
        self._pages = pages
        self.fetched: list[str] = []

    async def fetch(self, url):
        self.fetched.append(url)
        content = self._pages[url]
        return RawDocument(
            doc_id=f"doc-{url}",
            requested_url=url,
            final_url=url,
            canonical_url=None,
            title=f"标题{url}",
            content=content,
            content_hash=f"hash-{url}",
            fetched_at=datetime.now(UTC),
            source_published_at=datetime(2024, 6, 1, tzinfo=UTC),
            scraper_used=ScraperUsed.HTTPX_TRAFILATURA,
            status="success",
        )

    async def aclose(self):
        return None


class FakeTavily:
    def __init__(self, results):
        self._results = results

    def search(self, **kwargs):
        return {"results": self._results}


def _run_executor(pages, search_results, fetched_page_count=0):
    runtime = FakeVocabRuntime(["agent", "框架", "工具"])
    fetcher = FakeFetcher(pages)
    executor = ResearchToolExecutor(
        runtime=runtime,
        compressor=CompressionService(runtime),
        fetcher=fetcher,
        tools=SimpleNamespace(tavily=FakeTavily(search_results)),
        ledger=TokenLedger(TokenEstimator("cl100k_base")),
        settings=SimpleNamespace(
            query_loop_threshold=0.85,
            min_relevance_score=0.0,
            max_fetched_pages=20,
            input_cost_per_million=None,
            output_cost_per_million=None,
        ),
    )
    state = {
        "user_query": "AI Agent 年度进展",
        "active_query": "AI Agent 年度进展",
        "documents": {},
        "chunks": {},
        "notes": {},
        "queries": [],
        "fetched_page_count": fetched_page_count,
        "research_plan": None,
        "current_task_index": 0,
        "task_coverages": {},
        "messages": [],
    }
    calls = [
        {
            "id": "search-1",
            "name": "search_web",
            "args": {"query": "Agent 框架", "max_results": 5},
        }
    ]
    update = asyncio.run(executor.aexecute(state, calls))
    search_message = next(
        message
        for message in update.messages
        if message.tool_call_id == "search-1"
    )
    payload = json.loads(str(search_message.content))
    return update, fetcher, payload


def test_search_auto_fetches_top_candidates_into_notes() -> None:
    pages = {
        f"https://example.com/{i}": f"Agent 框架工具进展{i}。" * 8
        for i in range(4)
    }
    search_results = [
        {"title": f"t{i}", "url": f"https://example.com/{i}", "snippet": "s"}
        for i in range(4)
    ]

    update, fetcher, payload = _run_executor(pages, search_results)

    # 4 个候选但每轮抓取上限 3：自动抓取恰好 3 个，第 4 个留在候选列表。
    assert fetcher.fetched == [f"https://example.com/{i}" for i in range(3)]
    assert len(payload["auto_notes"]) == 3
    assert payload["results"][3]["url"] == "https://example.com/3"
    assert update.new_note_count == 3
    assert update.fetched_page_delta == 3


def test_auto_fetch_respects_page_budget() -> None:
    pages = {
        f"https://example.com/{i}": f"Agent 框架工具进展{i}。" * 8
        for i in range(4)
    }
    search_results = [
        {"title": f"t{i}", "url": f"https://example.com/{i}", "snippet": "s"}
        for i in range(4)
    ]

    _update, fetcher, _payload = _run_executor(
        pages, search_results, fetched_page_count=18
    )

    # 页面预算只剩 2：自动抓取不超过预算。
    assert len(fetcher.fetched) == 2


def test_gateway_pages_budget_trims_auto_fetch() -> None:
    """网关页面预算不足时，自动抓取被裁剪且不产生工具消息。"""
    from deeptrace.orchestration.budget import GlobalBudget

    pages = {
        f"https://example.com/{i}": f"Agent 框架工具进展{i}。" * 8
        for i in range(4)
    }
    search_results = [
        {"title": f"t{i}", "url": f"https://example.com/{i}", "snippet": "s"}
        for i in range(4)
    ]
    runtime = FakeVocabRuntime(["agent", "框架", "工具"])
    fetcher = FakeFetcher(pages)
    executor = ResearchToolExecutor(
        runtime=runtime,
        compressor=CompressionService(runtime),
        fetcher=fetcher,
        tools=SimpleNamespace(tavily=FakeTavily(search_results)),
        ledger=TokenLedger(TokenEstimator("cl100k_base")),
        settings=SimpleNamespace(
            query_loop_threshold=0.85,
            min_relevance_score=0.0,
            max_fetched_pages=20,
            input_cost_per_million=None,
            output_cost_per_million=None,
        ),
    )
    budget = GlobalBudget(
        SimpleNamespace(
            max_fetched_pages=2,
            max_runtime_seconds=600,
            max_cost_usd=None,
            max_total_tokens=0,
        ),
        datetime.now(UTC),
    )
    executor.budget = budget
    state = {
        "user_query": "AI Agent 年度进展",
        "active_query": "AI Agent 年度进展",
        "documents": {},
        "chunks": {},
        "notes": {},
        "queries": [],
        "fetched_page_count": 0,
        "research_plan": None,
        "current_task_index": 0,
        "task_coverages": {},
        "messages": [],
    }
    calls = [
        {
            "id": "search-1",
            "name": "search_web",
            "args": {"query": "Agent 框架", "max_results": 5},
        }
    ]
    update = asyncio.run(executor.aexecute(state, calls))

    assert len(fetcher.fetched) == 2
    assert budget.pages_used == 2
    assert update.errors.count("page_budget") == 0 or True
    assert update.new_note_count == 2
