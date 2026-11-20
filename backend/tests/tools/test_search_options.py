from datetime import date

import pytest

from deeptrace.tools.adapters import SearchWebArguments, _call_search
from deeptrace.tools.search.tavily import ToolContext, search_web


@pytest.mark.asyncio
async def test_search_options_reach_a_provider_that_accepts_them():
    received = {}

    async def provider(query, **options):
        received.update(query=query, **options)
        return {"ok": True, "results": []}

    await _call_search(
        provider,
        "quantum",
        max_results=8,
        search_depth="advanced",
        start_date="2026-01-01",
    )
    assert received == {
        "query": "quantum",
        "max_results": 8,
        "search_depth": "advanced",
        "start_date": "2026-01-01",
    }


def test_search_window_is_validated_before_execution():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        SearchWebArguments(
            query="research", start_date="2026-10-06", end_date="2026-01-01"
        )
    args = SearchWebArguments(
        query="research", search_depth="advanced", start_date="2026-01-01"
    )
    assert args.start_date == date(2026, 1, 1)


def test_advanced_discovery_passes_dates_and_result_count_to_tavily():
    class Provider:
        def search(self, **options):
            self.options = options
            return {"results": []}

    provider = Provider()
    result = search_web(
        ToolContext(tavily=provider),
        "quantum",
        max_results=8,
        search_depth="advanced",
        start_date="2026-01-01",
        end_date="2026-10-06",
    )
    assert result["ok"]
    assert provider.options["max_results"] == 8
    assert provider.options["search_depth"] == "advanced"
    assert provider.options["start_date"] == "2026-01-01"
    assert provider.options["end_date"] == "2026-10-06"


def test_site_path_becomes_domain_filter_and_foreign_results_are_removed():
    class Provider:
        def search(self, **options):
            self.options = options
            return {
                "results": [
                    {"url": "https://docs.example.com/v1/tasks", "title": "Docs"},
                    {"url": "https://other.example.com/tasks", "title": "Wrong domain"},
                ]
            }

    provider = Provider()
    result = search_web(
        ToolContext(tavily=provider), "site:docs.example.com/v1 task cancellation"
    )
    assert provider.options["include_domains"] == ["docs.example.com/v1"]
    assert [r["url"] for r in result["results"]] == [
        "https://docs.example.com/v1/tasks"
    ]


def test_version_search_path_is_not_lost_at_provider_boundary():
    class Provider:
        def search(self, **options):
            self.options = options
            return {'results': []}
    provider = Provider()
    search_web(ToolContext(tavily=provider),
               'site:docs.python.org/3.11/library/asyncio-task.html TaskGroup gather')
    assert provider.options['include_domains'] == ['docs.python.org/3.11/library/asyncio-task.html']
    assert provider.options['query'] == 'TaskGroup gather'


@pytest.mark.parametrize("query", ["site:[invalid fact", "-site:docs.example.com fact"])
def test_unrecognized_site_operator_does_not_crash_or_enable_domain_filter(query):
    class Provider:
        def search(self, **options):
            self.options = options
            return {"results": []}

    provider = Provider()
    assert search_web(ToolContext(tavily=provider), query)["ok"]
    assert "include_domains" not in provider.options


def test_site_filter_rejects_suffix_spoof_and_malformed_provider_urls():
    class Provider:
        def search(self, **options):
            return {
                "results": [
                    {"url": url}
                    for url in [
                        "https://docs.example.com.evil.org/fact",
                        "https://[invalid",
                        "https://sub.docs.example.com/fact",
                        "https://docs.example.com/fact",
                    ]
                ]
            }

    result = search_web(ToolContext(tavily=Provider()), "site:docs.example.com fact")
    assert {r["url"] for r in result["results"]} == {
        "https://sub.docs.example.com/fact",
        "https://docs.example.com/fact",
    }
