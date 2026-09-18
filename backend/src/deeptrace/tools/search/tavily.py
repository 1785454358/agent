"""Tavily 搜索实现。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from tavily import TavilyClient
from deeptrace.tools.search.ranking import rank_search_results


JsonObject = dict[str, Any]


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
    if (
        "connect" in name
        or "connection" in text
        or "http" in name
        or "network" in text
    ):
        return "http_failed"
    return "search_failed"


def search_web(
    context: ToolContext,
    query: str,
    max_results: int = 5,
    target_years: set[int] | None = None,
) -> JsonObject:
    """调用 Tavily 并仅回填标题、URL 和短摘要。"""
    clean_query = query.strip()
    if not clean_query:
        return _tool_error("invalid_query", "查询词不能为空")
    bounded = max(1, min(int(max_results), 8))
    try:
        response = context.tavily.search(
            query=clean_query,
            search_depth="basic",
            max_results=bounded,
            include_answer=False,
            include_raw_content=False,
        )
    except Exception as exc:
        return _tool_error(
            _classify_search_exception(exc),
            f"Tavily 请求失败：{type(exc).__name__}",
        )
    results: list[JsonObject] = []
    for item in response.get("results", []):
        url = str(item.get("url", "")).strip()
        if not url.startswith(("http://", "https://")):
            continue
        result = {
            "title": str(item.get("title", "")).strip() or url,
            "url": url,
            "snippet": str(item.get("content", "")).strip(),
            "score": item.get("score"),
        }
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
