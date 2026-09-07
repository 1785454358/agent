import asyncio

from deeptrace.multi_agent.resources import SharedResearchResources


class Fetcher:
    def __init__(self, document):
        self.document = document
        self.calls = 0

    async def fetch(self, url):
        self.calls += 1
        await asyncio.sleep(0)
        return self.document.model_copy(
            update={"requested_url": url, "final_url": url, "doc_id": url}
        )

    async def aclose(self):
        pass


def test_identical_concurrent_search_is_single_flight(raw_document):
    async def scenario():
        calls = 0

        async def search(query):
            nonlocal calls
            calls += 1
            await asyncio.sleep(0)
            return {
                "ok": True,
                "results": [
                    {"url": "https://example.com/a", "title": "A", "content": "x"}
                ],
            }

        resources = SharedResearchResources(search=search, fetcher=Fetcher(raw_document))
        leases = await resources.quota.allocate_initial(["r1", "r2"])
        first, second = await asyncio.gather(
            resources.search("same", leases["r1"]),
            resources.search("same", leases["r2"]),
        )
        assert calls == 1
        assert resources.quota.consumed == 1
        assert sorted([first.cached, second.cached]) == [False, True]

    asyncio.run(scenario())


def test_synchronous_search_is_offloaded_from_the_event_loop(
    raw_document, monkeypatch
):
    offloaded = []

    async def fake_to_thread(function, *args):
        offloaded.append(function)
        return function(*args)

    monkeypatch.setattr(asyncio, "to_thread", fake_to_thread)
    resources = SharedResearchResources(
        search=lambda query: {"ok": True, "results": []},
        fetcher=Fetcher(raw_document),
    )

    async def scenario():
        lease = (await resources.quota.allocate_initial(["r1"]))["r1"]
        result = await resources.search("query", lease)
        assert result.value["ok"]

    asyncio.run(scenario())
    assert len(offloaded) == 1


def test_identical_concurrent_fetch_is_single_flight(raw_document):
    async def scenario():
        fetcher = Fetcher(raw_document)
        resources = SharedResearchResources(search=lambda query: {}, fetcher=fetcher)
        leases = await resources.quota.allocate_initial(["r1", "r2"])
        first, second = await asyncio.gather(
            resources.fetch("https://example.com/a", leases["r1"]),
            resources.fetch("https://example.com/a", leases["r2"]),
        )
        assert fetcher.calls == 1
        assert resources.quota.consumed == 1
        assert sorted([first.cached, second.cached]) == [False, True]
        assert first.document.content == second.document.content

    asyncio.run(scenario())


def test_failed_network_attempt_is_charged_but_not_cached(raw_document):
    async def scenario():
        calls = 0

        async def search(query):
            nonlocal calls
            calls += 1
            return {"ok": False, "error": "search_failed"}

        resources = SharedResearchResources(search=search, fetcher=Fetcher(raw_document))
        lease = (await resources.quota.allocate_initial(["r1"]))["r1"]
        first = await resources.search("q", lease)
        second = await resources.search("q", lease)
        assert not first.value["ok"] and not second.value["ok"]
        assert calls == 2
        assert resources.quota.consumed == 2

    asyncio.run(scenario())


def test_identical_concurrent_failure_is_shared_but_later_retry_is_allowed(
    raw_document,
):
    async def scenario():
        calls = 0

        async def search(query):
            nonlocal calls
            calls += 1
            await asyncio.sleep(0)
            return {"ok": False, "error": "search_failed"}

        resources = SharedResearchResources(search=search, fetcher=Fetcher(raw_document))
        leases = await resources.quota.allocate_initial(["r1", "r2"])
        first, second = await asyncio.gather(
            resources.search("same failure", leases["r1"]),
            resources.search("same failure", leases["r2"]),
        )
        assert calls == 1
        assert resources.quota.consumed == 1
        assert not first.value["ok"] and not second.value["ok"]

        await resources.search("same failure", leases["r2"])
        assert calls == 2
        assert resources.quota.consumed == 2

    asyncio.run(scenario())
