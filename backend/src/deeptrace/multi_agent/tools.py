"""Task-local tools backed by run-owned Multi-Agent resources."""

from __future__ import annotations

import asyncio
import json
import re
from datetime import UTC, datetime, timedelta

from pydantic import ValidationError

from deeptrace.multi_agent.models import (
    FetchArgs,
    ResearchTopicArgs,
    SearchArgs,
    TargetedFetchArgs,
    TargetedResearchTopicArgs,
    TargetedSearchArgs,
)
from deeptrace.tools.scraper import normalize_url_before_fetch

SEARCH_RESULT_LIMIT = 3
SEARCH_TITLE_CHARS = 200
SEARCH_SNIPPET_CHARS = 300
RESEARCHER_CONTEXT_CHARS = 1_200


class ResearcherTools:
    """Keep one Researcher's known URLs, read sources, and queries isolated."""

    def __init__(self, assignment, resources, lease, *, user_question: str = ""):
        self.assignment = assignment
        self.resources = resources
        self.lease = lease
        self.known_urls: set[str] = set()
        self.read_sources: set[str] = set()
        self.queries: list[str] = []
        self._cache: dict[str, dict] = {}
        for value in (user_question, assignment.objective):
            for url in re.findall(r"https?://[^\s<>，。；）)\]]+", value):
                try:
                    self.known_urls.add(normalize_url_before_fetch(url))
                except ValueError:
                    continue

    async def execute(self, name: str, args: dict) -> dict:
        schemas = {
            "research_topic": TargetedResearchTopicArgs,
            "search_web": SearchArgs,
            "fetch_page": TargetedFetchArgs,
            "search_memory": TargetedSearchArgs,
        }
        schema = schemas.get(name)
        if schema is None:
            return {"ok": False, "error": "unknown_tool"}
        try:
            parsed = schema.model_validate(args)
        except ValidationError:
            return {"ok": False, "error": "invalid_arguments"}
        key = name + json.dumps(parsed.model_dump(), ensure_ascii=False, sort_keys=True)
        if key in self._cache:
            return {**self._cache[key], "cached": True}
        handler = {
            "research_topic": self._research_topic,
            "search_web": self._search,
            "fetch_page": self._fetch,
            "search_memory": self._memory_search,
        }[name]
        try:
            result = await handler(parsed)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - isolate and sanitize tool failures
            result = {"ok": False, "error": type(exc).__name__}
        if result.get("ok"):
            self._cache[key] = result
        return result

    async def _search(self, args: SearchArgs) -> dict:
        if args.query not in self.queries:
            self.queries.append(args.query)
        outcome = await self.resources.search(args.query, self.lease)
        payload = outcome.value
        if not payload.get("ok"):
            error = payload.get("error", "search_failed")
            if isinstance(error, dict):
                error = error.get("code", "search_failed")
            return {"ok": False, "error": str(error)}
        results = []
        for item in payload.get("results", [])[:SEARCH_RESULT_LIMIT]:
            if not isinstance(item, dict):
                continue
            try:
                url = normalize_url_before_fetch(item.get("url", ""))
            except (TypeError, ValueError):
                continue
            self.known_urls.add(url)
            results.append(
                {
                    "url": url,
                    "title": str(item.get("title", ""))[:SEARCH_TITLE_CHARS],
                    "snippet": str(
                        item.get("snippet", item.get("content", ""))
                    )[:SEARCH_SNIPPET_CHARS],
                }
            )
        return {"ok": True, "results": results, "cached": outcome.cached}

    async def _fetch(self, args: FetchArgs) -> dict:
        try:
            url = normalize_url_before_fetch(args.url)
        except (TypeError, ValueError):
            return {"ok": False, "error": "invalid_url"}
        if url not in self.known_urls:
            return {
                "ok": False,
                "error": "unknown_url",
                "hint": "先搜索或检索记忆，再读取返回的 URL",
            }
        outcome = await self.resources.fetch(url, self.lease, refresh=args.refresh)
        if outcome.error:
            return {"ok": False, "error": outcome.error}
        try:
            source, context = await self.resources.ingest(
                self.assignment.id, self.assignment.objective, outcome.document
            )
        except ValueError:
            return {"ok": False, "error": "no_relevant_content"}
        self.known_urls.add(source)
        self.read_sources.add(source)
        document = outcome.document
        return {
            "ok": True,
            "url": source,
            "context": context[:RESEARCHER_CONTEXT_CHARS],
            "cached": outcome.cached,
            "fetched_at": document.fetched_at.isoformat(),
            "published_at": document.source_published_at.isoformat()
            if document.source_published_at
            else None,
        }

    async def _research_topic(self, args: ResearchTopicArgs) -> dict:
        search_result = await self._search(SearchArgs(query=args.query))
        if not search_result.get("ok"):
            return search_result
        urls = []
        for item in search_result.get("results", []):
            if item["url"] not in urls:
                urls.append(item["url"])
            if len(urls) >= args.max_pages:
                break
        pages = await asyncio.gather(
            *(self._fetch(FetchArgs(url=url)) for url in urls)
        )
        return {
            "ok": True,
            "query": args.query,
            "fetched": sum(bool(page.get("ok")) for page in pages),
            "pages": pages,
        }

    async def _memory_search(self, args: SearchArgs) -> dict:
        memory = self.resources.memory
        if memory is None:
            return {"ok": False, "error": "memory_disabled"}
        max_age = getattr(
            self.resources.settings, "multi_agent_memory_max_age_days", 7
        )
        cutoff = datetime.now(UTC) - timedelta(days=max_age)
        entries = await asyncio.to_thread(memory.entries)
        recent = [
            entry
            for entry in entries
            if entry.fetched_at.replace(tzinfo=entry.fetched_at.tzinfo or UTC) >= cutoff
        ]
        # Keep the memory lookup local and bounded. BGE re-ranking remains in context
        # ingestion, so this coordination path adds no LLM compression call.
        tokens = {token.lower() for token in re.findall(r"\w+", args.query)}
        ranked = sorted(
            recent,
            key=lambda entry: len(
                tokens & {token.lower() for token in re.findall(r"\w+", entry.title)}
            ),
            reverse=True,
        )[:3]
        results = []
        for entry in ranked:
            url = normalize_url_before_fetch(entry.url)
            self.known_urls.add(url)
            self.resources.cache_memory_document(url, memory.entry_to_document(entry))
            results.append(
                {
                    "url": url,
                    "title": entry.title[:SEARCH_TITLE_CHARS],
                    "fetched_at": entry.fetched_at.isoformat(),
                    "snippet": entry.content[:SEARCH_SNIPPET_CHARS],
                }
            )
        return {"ok": True, "results": results}
