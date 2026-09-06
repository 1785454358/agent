import asyncio

from deeptrace.multi_agent.models import ResearchAssignment, ResearcherResult
from deeptrace.multi_agent.resources import SharedResearchResources
from deeptrace.multi_agent.tools import ResearcherTools


class Fetcher:
    def __init__(self, document):
        self.document = document
        self.calls = 0

    async def fetch(self, url):
        self.calls += 1
        return self.document.model_copy(
            update={"requested_url": url, "final_url": url, "doc_id": url}
        )

    async def aclose(self):
        pass


class Compressor:
    async def aget_context(self, query, documents, max_results=5):
        return f"Source: {documents[0].final_url}\n{query}\n{documents[0].content}"


class LongCompressor:
    async def aget_context(self, query, documents, max_results=5):
        return "X" * 5_000


def assignment(task_id="r1", objective="研究技术"):
    return ResearchAssignment(
        id=task_id,
        objective=objective,
        required_outputs=["代表性进展"],
        excluded_scope=[],
        source_guidance=["官方来源"],
    )


def build(raw_document):
    async def search(query):
        return {
            "ok": True,
            "results": [
                {"url": "https://example.com/a", "title": "A", "content": "摘要"},
                {"url": "https://example.com/b", "title": "B", "content": "摘要"},
            ],
        }

    return SharedResearchResources(
        search=search,
        fetcher=Fetcher(raw_document),
        compressor=Compressor(),
        total_tool_calls=20,
        per_researcher_tool_calls=10,
    )


def test_search_snippets_do_not_count_as_read_sources(raw_document):
    async def scenario():
        resources = build(raw_document)
        lease = (await resources.quota.allocate_initial(["r1"]))["r1"]
        tools = ResearcherTools(assignment(), resources, lease)
        result = await tools.execute("search_web", {"query": "q"})
        assert result["ok"]
        assert tools.read_sources == set()
        assert "https://example.com/a" in tools.known_urls

    asyncio.run(scenario())


def test_search_payload_is_navigation_sized(raw_document):
    async def search(query):
        return {
            "ok": True,
            "results": [
                {
                    "url": f"https://example.com/{index}",
                    "title": "T" * 400,
                    "snippet": "S" * 1_000,
                }
                for index in range(5)
            ],
        }

    resources = SharedResearchResources(search=search, fetcher=Fetcher(raw_document))

    async def scenario():
        lease = (await resources.quota.allocate_initial(["r1"]))["r1"]
        tools = ResearcherTools(assignment(), resources, lease)
        result = await tools.execute("search_web", {"query": "q"})
        assert len(result["results"]) == 3
        assert all(len(item["title"]) <= 200 for item in result["results"])
        assert all(len(item["snippet"]) <= 300 for item in result["results"])

    asyncio.run(scenario())


def test_fetch_payload_is_smaller_than_writer_context(raw_document):
    async def search(query):
        return {
            "ok": True,
            "results": [{"url": "https://example.com/a", "title": "A"}],
        }

    resources = SharedResearchResources(
        search=search,
        fetcher=Fetcher(raw_document),
        compressor=LongCompressor(),
    )

    async def scenario():
        lease = (await resources.quota.allocate_initial(["r1"]))["r1"]
        tools = ResearcherTools(assignment(), resources, lease)
        await tools.execute("search_web", {"query": "q"})
        fetched = await tools.execute(
            "fetch_page",
            {
                "url": "https://example.com/a",
                "target_output": "代表性进展",
            },
        )
        assert len(fetched["context"]) == 1_200
        assert len(resources.context_for("r1", "https://example.com/a")) == 3_000

    asyncio.run(scenario())


def test_search_exposes_service_snippet_and_normalizes_structured_error(
    raw_document,
):
    responses = [
        {
            "ok": True,
            "results": [
                {
                    "url": "https://example.com/a",
                    "title": "A",
                    "snippet": "服务返回的摘要",
                }
            ],
        },
        {"ok": False, "error": {"code": "search_failed", "message": "hidden"}},
    ]

    def search(query):
        return responses.pop(0)

    resources = SharedResearchResources(search=search, fetcher=Fetcher(raw_document))

    async def scenario():
        lease = (await resources.quota.allocate_initial(["r1"]))["r1"]
        tools = ResearcherTools(assignment(), resources, lease)
        first = await tools.execute("search_web", {"query": "first"})
        second = await tools.execute("search_web", {"query": "second"})
        assert first["results"][0]["snippet"] == "服务返回的摘要"
        assert second == {"ok": False, "error": "search_failed"}

    asyncio.run(scenario())


def test_cached_page_is_task_local_read_without_network_charge(raw_document):
    async def scenario():
        resources = build(raw_document)
        leases = await resources.quota.allocate_initial(["r1", "r2"])
        first = ResearcherTools(assignment("r1", "技术"), resources, leases["r1"])
        second = ResearcherTools(assignment("r2", "政策"), resources, leases["r2"])
        await first.execute("search_web", {"query": "q"})
        await second.execute("search_web", {"query": "q"})
        await first.execute(
            "fetch_page",
            {
                "url": "https://example.com/a",
                "target_output": "代表性进展",
            },
        )
        before = resources.quota.consumed
        result = await second.execute(
            "fetch_page",
            {
                "url": "https://example.com/a",
                "target_output": "代表性进展",
            },
        )
        assert result["ok"] and result["cached"]
        assert resources.quota.consumed == before
        assert second.read_sources == {"https://example.com/a"}
        assert "政策" in resources.context_for("r2", "https://example.com/a")

    asyncio.run(scenario())


def test_unknown_url_is_rejected_before_fetch(raw_document):
    async def scenario():
        resources = build(raw_document)
        lease = (await resources.quota.allocate_initial(["r1"]))["r1"]
        tools = ResearcherTools(assignment(), resources, lease)
        result = await tools.execute(
            "fetch_page",
            {
                "url": "https://untrusted.example/guessed",
                "target_output": "代表性进展",
            },
        )
        assert result["error"] == "unknown_url"
        assert resources.quota.consumed == 0

    asyncio.run(scenario())


def test_research_topic_charges_search_and_each_fetch(raw_document):
    async def scenario():
        resources = build(raw_document)
        lease = (await resources.quota.allocate_initial(["r1"]))["r1"]
        tools = ResearcherTools(assignment(), resources, lease)
        result = await tools.execute(
            "research_topic",
            {
                "query": "q",
                "max_pages": 2,
                "target_output": "代表性进展",
            },
        )
        assert result["fetched"] == 2
        assert resources.quota.consumed == 3
        assert len(tools.read_sources) == 2

    asyncio.run(scenario())


def test_writer_material_uses_only_result_sources(raw_document):
    async def scenario():
        resources = build(raw_document)
        leases = await resources.quota.allocate_initial(["r1", "r2"])
        first = ResearcherTools(assignment("r1", "技术"), resources, leases["r1"])
        second = ResearcherTools(assignment("r2", "政策"), resources, leases["r2"])
        await first.execute(
            "research_topic",
            {
                "query": "q",
                "max_pages": 1,
                "target_output": "代表性进展",
            },
        )
        await second.execute(
            "research_topic",
            {
                "query": "q",
                "max_pages": 2,
                "target_output": "代表性进展",
            },
        )
        results = [
            ResearcherResult(
                task_id="r1",
                status="completed",
                summary="完成",
                source_urls=["https://example.com/a"],
                gaps=[],
                stop_reason="completed",
            ),
            ResearcherResult(
                task_id="r2",
                status="partial",
                summary="部分",
                source_urls=["https://example.com/b"],
                gaps=["仍需核对"],
                stop_reason="round_limit",
            ),
        ]
        context, sources = resources.writer_material(results, max_chars=10_000)
        assert sources == ["https://example.com/a", "https://example.com/b"]
        assert "https://example.com/a" in context
        assert "https://example.com/b" in context

    asyncio.run(scenario())


def test_writer_material_never_returns_a_source_missing_from_bounded_context(
    raw_document,
):
    resources = build(raw_document)
    resources._contexts = {
        "r1": {"https://example.com/a": "A" * 100},
        "r2": {"https://example.com/b": "B" * 100},
    }
    results = [
        ResearcherResult(
            task_id="r1",
            status="completed",
            summary="A",
            source_urls=["https://example.com/a"],
            gaps=[],
            stop_reason="completed",
        ),
        ResearcherResult(
            task_id="r2",
            status="completed",
            summary="B",
            source_urls=["https://example.com/b"],
            gaps=[],
            stop_reason="completed",
        ),
    ]
    context, sources = resources.writer_material(results, max_chars=60)
    assert len(context) <= 60
    assert all(source in context for source in sources)
