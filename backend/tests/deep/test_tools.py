import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import numpy as np

from deeptrace.deep.tools import ResearchToolbox
from deeptrace.memory import ResearchMemory


class SemanticRuntime:
    def embed(self, texts):
        return np.array([[1.0, 0.0] if "相关" in t else [0.0, 1.0] for t in texts])

    def query_vector(self, query):
        return np.array([1.0, 0.0])


def test_memory_retrieval_ranks_semantically_and_excludes_stale_pages(
    tmp_path, raw_document
):
    memory = ResearchMemory(tmp_path / "pages.jsonl")
    memory.add_documents(
        [
            raw_document.model_copy(update={"title": "无关", "content": "别的内容"}),
            raw_document.model_copy(
                update={"final_url": "https://example.com/b", "title": "相关资料"}
            ),
            raw_document.model_copy(
                update={
                    "final_url": "https://example.com/old",
                    "title": "相关旧资料",
                    "fetched_at": datetime.now(UTC) - timedelta(days=30),
                }
            ),
        ]
    )
    toolbox = ResearchToolbox(
        search=None,
        fetcher=None,
        compressor=None,
        settings=SimpleNamespace(deep_memory_max_age_days=7),
        memory=memory,
        runtime=SemanticRuntime(),
    )
    result = asyncio.run(toolbox.execute("search_memory", {"query": "部署方案"}))
    assert result["ok"]
    assert [item["url"] for item in result["results"]] == ["https://example.com/b"]
    assert "fetched_at" in result["results"][0]
    assert not toolbox.documents  # retrieval alone is not a read


def test_successful_search_is_cached_and_unknown_tool_is_rejected():
    calls = []

    async def search(query):
        calls.append(query)
        return {"ok": True, "results": []}

    toolbox = ResearchToolbox(
        search=search, fetcher=None, compressor=None, settings=SimpleNamespace()
    )

    async def run():
        first = await toolbox.execute("search_web", {"query": "same"})
        second = await toolbox.execute("search_web", {"query": "same"})
        bad = await toolbox.execute("shell", {"command": "anything"})
        return first, second, bad

    first, second, bad = asyncio.run(run())
    assert calls == ["same"]
    assert first["ok"] and second["cached"]
    assert bad["error"] == "unknown_tool"


def test_cached_page_can_be_explicitly_refreshed(raw_document):
    from deeptrace.context import ContextCompressor

    class Fetcher:
        calls = 0

        async def fetch(self, url):
            self.calls += 1
            return raw_document.model_copy(update={"content": "最新网页内容"})

    fetcher = Fetcher()
    toolbox = ResearchToolbox(
        search=None,
        fetcher=fetcher,
        compressor=ContextCompressor(None),
        settings=SimpleNamespace(),
    )
    toolbox.known_urls.add("https://example.com/a")
    toolbox.cached_pages["https://example.com/a"] = raw_document

    async def run():
        cached = await toolbox.execute("fetch_page", {"url": "https://example.com/a"})
        refreshed = await toolbox.execute(
            "fetch_page", {"url": "https://example.com/a", "refresh": True}
        )
        reread = await toolbox.execute("fetch_page", {"url": "https://example.com/a"})
        return cached, refreshed, reread

    cached, refreshed, reread = asyncio.run(run())
    assert raw_document.content in cached["context"]
    assert refreshed["ok"]
    assert "最新网页内容" in refreshed["context"]
    assert fetcher.calls == 1
    assert "最新网页内容" in reread["context"]
