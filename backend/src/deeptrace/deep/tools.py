"""Bounded read-only tools over the existing search, scraper and page memory."""

import asyncio
from datetime import UTC, datetime, timedelta
import inspect
import json
import re

from pydantic import ValidationError

from deeptrace.deep.models import ReadArgs, ResearchTopicArgs, SearchArgs
from deeptrace.tools.scraper import normalize_url_before_fetch


class ResearchToolbox:
    def __init__(
        self, *, search, fetcher, compressor, settings, memory=None, runtime=None
    ):
        self.search = search
        self.fetcher = fetcher
        self.compressor = compressor
        self.settings = settings
        self.memory = memory
        self.embeddings = runtime
        # 可选的工具配额回调，由 agent 在每轮运行前注入，组合工具内部按
        # 实际抓取页数计数，不能用组合工具绕过调用上限。
        self.quota = None
        self.reset()

    def reset(self):
        self.documents = {}
        self.contexts: dict[str, str] = {}
        self.queries: list[str] = []
        self.known_urls: set[str] = set()
        self.cached_pages = {}
        self._cache: dict[str, dict] = {}
        self._attempts: dict[str, int] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self.pages_used = 0

    def set_question(self, question: str):
        self.question = question
        for url in re.findall(r"https?://[^\s<>，。；）)\]]+", question):
            try:
                self.known_urls.add(normalize_url_before_fetch(url))
            except ValueError:
                continue

    async def execute(self, name: str, args: dict) -> dict:
        schemas = {
            "research_topic": ResearchTopicArgs,
            "search_web": SearchArgs,
            "fetch_page": ReadArgs,
            "search_memory": SearchArgs,
        }
        if name not in schemas:
            return {"ok": False, "error": "unknown_tool"}
        try:
            parsed = schemas[name].model_validate(args)
        except ValidationError:
            return {"ok": False, "error": "invalid_arguments"}
        key = name + json.dumps(parsed.model_dump(), sort_keys=True, ensure_ascii=False)
        async with self._locks.setdefault(key, asyncio.Lock()):
            if key in self._cache:
                return {**self._cache[key], "cached": True}
            if self._attempts.get(key, 0) >= 2:
                return {"ok": False, "error": "repeat_limit"}
            self._attempts[key] = self._attempts.get(key, 0) + 1
            try:
                handler = {
                    "research_topic": self._research_topic,
                    "search_web": self._search,
                    "fetch_page": self._read,
                    "search_memory": self._memory_search,
                }[name]
                result = await handler(parsed)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                # Do not echo Provider errors, which may contain credentials or headers.
                result = {"ok": False, "error": type(exc).__name__}
            if result.get("ok"):
                if name == "fetch_page" and parsed.refresh:
                    stale_key = name + json.dumps(
                        ReadArgs(url=parsed.url).model_dump(),
                        sort_keys=True,
                        ensure_ascii=False,
                    )
                    self._cache.pop(stale_key, None)
                self._cache[key] = result
            return result

    async def _search(self, args: SearchArgs) -> dict:
        if args.query not in self.queries:
            self.queries.append(args.query)
        if inspect.iscoroutinefunction(self.search):
            payload = await self.search(args.query)
        else:
            payload = await asyncio.to_thread(self.search, args.query)
            if inspect.isawaitable(payload):
                payload = await payload
        if not isinstance(payload, dict) or not payload.get("ok"):
            return {"ok": False, "error": "search_failed"}
        results = []
        for item in payload.get("results", [])[:5]:
            if not isinstance(item, dict):
                continue
            try:
                url = normalize_url_before_fetch(item.get("url", ""))
            except (ValueError, TypeError):
                continue
            self.known_urls.add(url)
            results.append(
                {
                    "url": url,
                    "title": str(item.get("title", ""))[:300],
                    "snippet": str(item.get("content", ""))[:800],
                }
            )
        return {"ok": True, "results": results}

    async def _read(self, args: ReadArgs) -> dict:
        url = normalize_url_before_fetch(args.url)
        if url not in self.known_urls:
            return {
                "ok": False,
                "error": "unknown_url",
                "hint": "先搜索或检索记忆，再阅读返回的 URL",
            }
        document = None if args.refresh else self.cached_pages.get(url)
        if document is None:
            self.pages_used += 1
            document = await self.fetcher.fetch(url)
            self.cached_pages[url] = document
        return await self._ingest_document(document)

    async def _ingest_document(self, document) -> dict:
        """抓取后的共用处理：校验、压缩、入库，返回精简片段。

        原文全文留在 self.contexts 供 Writer 使用，返回给 Executor 的只是
        决策参考用的截断片段。
        """
        if document.status != "success" or not document.content.strip():
            return {"ok": False, "error": "empty_page"}
        source = document.final_url or document.requested_url
        context = await self.compressor.aget_context(
            getattr(self, "question", "研究资料"), [document], max_results=5
        )
        if not context.strip():
            return {"ok": False, "error": "no_relevant_content"}
        self.documents[source] = document
        self.contexts[source] = context[:6000]
        return {
            "ok": True,
            "url": source,
            "context": context[:2000],
            "fetched_at": document.fetched_at.isoformat(),
            "published_at": document.source_published_at.isoformat()
            if document.source_published_at
            else None,
        }

    async def _research_topic(self, args: ResearchTopicArgs) -> dict:
        """组合工具：搜索 → 去重 → 候选筛选 → 批量抓取，一次完成。

        确定性步骤在工具层完成，模型只需决定研究方向。内部每次实际抓取
        都通过 self.quota 计入工具配额，不能用组合工具绕过调用上限。
        """
        search_result = await self._search(SearchArgs(query=args.query))
        if not search_result.get("ok"):
            return search_result
        candidates = search_result.get("results", [])
        if not candidates:
            return {"ok": True, "query": args.query, "pages": [], "fetched": 0}

        # 候选筛选：去重后按顺序取前 max_pages 个（搜索结果已按相关性排序）。
        seen = set()
        urls = []
        for item in candidates:
            url = item["url"]
            if url in seen:
                continue
            seen.add(url)
            urls.append(url)
            if len(urls) >= args.max_pages:
                break

        async def fetch_one(url: str) -> dict:
            # 每次实际抓取都计入配额；配额不足则跳过该页。
            if self.quota is not None and not self.quota():
                return {"url": url, "ok": False, "error": "tool_call_limit"}
            if url in self.cached_pages:
                return await self._ingest_document(self.cached_pages[url])
            try:
                self.pages_used += 1
                document = await self.fetcher.fetch(url)
                self.cached_pages[url] = document
            except Exception as exc:
                return {"url": url, "ok": False, "error": type(exc).__name__}
            return await self._ingest_document(document)

        pages = await asyncio.gather(*(fetch_one(url) for url in urls))
        ok_pages = [p for p in pages if p.get("ok")]
        return {
            "ok": True,
            "query": args.query,
            "fetched": len(ok_pages),
            "pages": pages,
        }

    async def _memory_search(self, args: SearchArgs) -> dict:
        if self.memory is None or self.embeddings is None:
            return {"ok": False, "error": "memory_disabled", "hint": "改用 search_web"}
        entries = await asyncio.to_thread(self.memory.entries)
        cutoff = datetime.now(UTC) - timedelta(
            days=getattr(self.settings, "deep_memory_max_age_days", 7)
        )
        recent = sorted(
            (
                e
                for e in entries
                if e.fetched_at.replace(tzinfo=e.fetched_at.tzinfo or UTC) >= cutoff
            ),
            key=lambda e: e.fetched_at.timestamp(),
            reverse=True,
        )[:100]
        if not recent:
            return {"ok": True, "results": []}

        def rank():
            vectors = self.embeddings.embed(
                [e.title + "\n" + e.content[:2000] for e in recent]
            )
            scores = vectors @ self.embeddings.query_vector(args.query)
            return sorted(
                (
                    (float(score), i)
                    for i, score in enumerate(scores)
                    if float(score) >= 0.42
                ),
                reverse=True,
            )[:3]

        results = []
        for score, index in await asyncio.to_thread(rank):
            entry = recent[index]
            url = normalize_url_before_fetch(entry.url)
            self.known_urls.add(url)
            self.cached_pages.setdefault(url, self.memory.entry_to_document(entry))
            results.append(
                {
                    "url": url,
                    "title": entry.title[:300],
                    "score": round(score, 4),
                    "fetched_at": entry.fetched_at.isoformat(),
                    "snippet": entry.content[:500],
                    "notice": "历史页面，涉及最新事实时应网络核验",
                }
            )
        return {"ok": True, "results": results}

    async def persist(self):
        if self.memory and self.documents:
            await asyncio.to_thread(
                self.memory.add_documents, list(self.documents.values())
            )

    def relevant_contexts(
        self, objective: str, *, max_sources: int = 3, per_source_chars: int = 800
    ) -> str:
        """按任务目标用 BGE 筛选最相关来源片段，供 Executor 决策参考。

        原文全文仍保留在 self.contexts 供 Writer 使用；这里只返回少量
        与当前任务最相关的截断片段，避免每轮重复携带全部已读原文。
        """
        if not self.contexts or self.embeddings is None:
            return ""
        sources = list(self.contexts)
        texts = [self.contexts[s] for s in sources]
        try:
            vectors = self.embeddings.embed(texts)
            scores = vectors @ self.embeddings.query_vector(objective)
        except Exception:
            # 嵌入失败时退化为按插入顺序取前几个来源，保证决策仍有参考。
            ranked = list(range(len(sources)))[:max_sources]
        else:
            ranked = sorted(
                range(len(sources)), key=lambda i: float(scores[i]), reverse=True
            )[:max_sources]
        parts = [
            f"Source: {sources[i]}\n{texts[i][:per_source_chars]}" for i in ranked
        ]
        return "\n\n".join(parts)

    async def aclose(self):
        if self.fetcher:
            await self.fetcher.aclose()
