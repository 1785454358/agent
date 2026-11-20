"""Tavily 搜索实现。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from tavily import TavilyClient

from deeptrace.tools.search.ranking import rank_search_results

JsonObject = dict[str, Any]


def _site_options(query: str) -> tuple[str, list[str]]:
    domains = []

    def replace(match):
        try:
            value = urlsplit("https://" + match.group(1).strip("\"'"))
        except ValueError:
            return match.group(0)
        host = (value.hostname or "").lower().rstrip(".")
        if (
            not host
            or value.username
            or value.password
            or not re.fullmatch(r"[a-z0-9.-]+", host)
        ):
            return match.group(0)
        scope = host + value.path.rstrip('/')
        if scope not in domains:
            domains.append(scope)
        # Tavily accepts host/path scopes in include_domains. Converting the
        # version path to plain query words loses the targeted documentation.
        return ''

    cleaned = re.sub(r"(?<!\S)site:([^\s]+)", replace, query)
    return " ".join(cleaned.split()) or query, domains[:8]


@dataclass
class ToolContext:
    """搜索服务依赖；抓取器由 LangGraph 节点单独管理。"""

    tavily: TavilyClient


def _tool_error(code: str, message: str, **details: Any) -> JsonObject:
    return {
        "ok": False,
        "error": {"code": code, "message": message, "details": details},
    }


def _classify_search_exception(exc: Exception) -> str:
    """Map a provider exception to a code the gateway can classify.

    Timeouts and rate limits are transient (the gateway retries with backoff);
    anything else stays recoverable so the model can reformulate its query.
    """
    name = type(exc).__name__.casefold()
    text = str(exc).casefold()
    if "timeout" in name or "timed out" in text or "timeout" in text:
        return "provider_timeout"
    if any(token in text for token in ("429", "rate limit", "too many requests")):
        return "http_failed"
    if "connect" in name or "connection" in text or "http" in name or "network" in text:
        return "http_failed"
    return "search_failed"


def search_web(
    context: ToolContext,
    query: str,
    max_results: int = 5,
    target_years: set[int] | None = None,
    *,
    search_depth: str = "basic",
    start_date: str | None = None,
    end_date: str | None = None,
) -> JsonObject:
    """调用 Tavily 并仅回填标题、URL 和短摘要。"""
    clean_query = query.strip()
    if not clean_query:
        return _tool_error("invalid_query", "查询词不能为空")
    bounded = max(1, min(int(max_results), 8))
    provider_query, domains = _site_options(clean_query)
    try:
        date_options = {
            key: value
            for key, value in (("start_date", start_date), ("end_date", end_date))
            if value
        }
        if date_options:
            date_options.update(
                include_published_date=True, filter_by_published_date=True
            )
        response = context.tavily.search(
            query=provider_query,
            search_depth=search_depth,
            max_results=bounded,
            include_answer=False,
            include_raw_content=False,
            **({"include_domains": domains} if domains else {}),
            **date_options,
        )
    except Exception as exc:  # noqa: BLE001 - isolate external search-provider failures
        return _tool_error(
            _classify_search_exception(exc),
            f"Tavily 请求失败：{type(exc).__name__}",
        )
    results: list[JsonObject] = []
    for item in response.get("results", []):
        url = str(item.get("url", "")).strip()
        if not url.startswith(("http://", "https://")):
            continue
        try:
            host = (urlsplit(url).hostname or "").lower().rstrip(".")
        except ValueError:
            continue
        if domains and not any(
            (host == scope.hostname or host.endswith('.' + scope.hostname))
            and (not scope.path or urlsplit(url).path == scope.path
                 or urlsplit(url).path.startswith(scope.path + '/'))
            for scope in (urlsplit('https://' + d) for d in domains)
        ):
            continue
        result = {
            "title": str(item.get("title", "")).strip() or url,
            "url": url,
            "snippet": str(item.get("content", "")).strip(),
            "score": item.get("score"),
        }
        if isinstance(item.get("published_date"), str):
            result["discovery_date"] = item["published_date"][:128]
        raw_content = item.get("raw_content")
        if isinstance(raw_content, str) and raw_content.strip():
            result["raw_content"] = raw_content.strip()
        results.append(result)
    results = rank_search_results(results, clean_query, target_years or set())
    return {
        "ok": True,
        "query": clean_query,
        "results": results[:bounded],
        "notice": "搜索摘要只是候选线索，不是已验证证据。",
    }
