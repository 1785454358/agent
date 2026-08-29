from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx
from tavily import TavilyClient


JsonObject = dict[str, Any]


@dataclass
class ToolContext:
    tavily: TavilyClient
    http: httpx.Client | None
    max_page_chars: int
    fetched_urls: set[str] = field(default_factory=set)


def _tool_error(code: str, message: str, **details: Any) -> JsonObject:
    return {
        "ok": False,
        "error": {
            "code": code,
            "message": message,
            "details": details,
        },
    }


def search_web(
    context: ToolContext,
    query: str,
    max_results: int = 5,
) -> JsonObject:
    clean_query = query.strip()
    if not clean_query:
        return _tool_error("invalid_query", "query must not be empty")

    bounded_max_results = max(1, min(int(max_results), 5))
    try:
        response = context.tavily.search(
            query=clean_query,
            search_depth="basic",
            max_results=bounded_max_results,
            include_answer=False,
            include_raw_content=False,
        )
    except Exception as exc:
        return _tool_error(
            "search_failed",
            f"Tavily request failed with {type(exc).__name__}",
        )

    normalized: list[JsonObject] = []
    for item in response.get("results", []):
        url = str(item.get("url", "")).strip()
        if not url.startswith(("http://", "https://")):
            continue
        normalized.append(
            {
                "title": str(item.get("title", "")).strip() or url,
                "url": url,
                "snippet": str(item.get("content", "")).strip(),
                "score": item.get("score"),
            }
        )

    return {
        "ok": True,
        "query": clean_query,
        "results": normalized[:bounded_max_results],
        "notice": "Search snippets are discovery hints, not verified evidence.",
    }
