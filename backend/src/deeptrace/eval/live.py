"""Explicit live-web evaluation entry point."""

import asyncio

from deeptrace.eval.env import build_eval_context


def retrieval_identity(settings):
    return {
        "search": "tavily",
        "fetch": "AsyncWebFetcher",
        "search_depth": "basic",
        "max_results": 5,
        "min_chars": settings.min_extracted_chars,
        "min_tokens": settings.min_extracted_tokens,
        "max_page_chars": settings.max_page_chars,
        "allow_benchmark_dns_proxy": settings.allow_benchmark_dns_proxy,
    }


def environment_factory(settings):
    from tavily import TavilyClient

    from deeptrace.tools.scraper.fetcher import AsyncWebFetcher
    from deeptrace.tools.search.tavily import ToolContext, search_web

    class LiveSearch:
        async def search(self, query):
            return await asyncio.to_thread(
                search_web,
                ToolContext(tavily=TavilyClient(api_key=settings.tavily_api_key)),
                query,
            )

    def build(corpus, **kwargs):
        fetcher = AsyncWebFetcher(
            min_chars=settings.min_extracted_chars,
            min_tokens=settings.min_extracted_tokens,
            max_page_chars=settings.max_page_chars,
            allow_benchmark_dns_proxy=settings.allow_benchmark_dns_proxy,
        )
        return build_eval_context(
            corpus, search=LiveSearch(), fetcher=fetcher, **kwargs
        )

    return build


def main(argv=None):
    from deeptrace.eval.__main__ import main as eval_main

    return eval_main(argv, live_web=True)


if __name__ == "__main__":
    raise SystemExit(main())
