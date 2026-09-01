"""搜索候选的时间、来源与域名多样性排序。"""

import re
from typing import Any, Sequence
from urllib.parse import urlsplit

from tld import get_fld

_PRIMARY_HOSTS = ("arxiv.org", "openai.com", "microsoft.com", "google.com", "anthropic.com", ".gov")
_WEAK = ("best", "top ", "榜单", "排名")


def registered_domain(url: str) -> str:
    return get_fld(url, fail_silently=True) or (urlsplit(url).hostname or url)


def rank_search_results(results: Sequence[dict[str, Any]], query: str, target_years: set[int]) -> list[dict[str, Any]]:
    """按相关度、目标年份、一手特征和域名多样性稳定排序。"""
    scored: list[tuple[float, int, dict[str, Any]]] = []
    for index, source in enumerate(results):
        item = dict(source)
        text = f"{item.get('title', '')} {item.get('snippet', item.get('content', ''))}".lower()
        host = (urlsplit(str(item.get("url", ""))).hostname or "").lower()
        domain = registered_domain(str(item.get("url", "")))
        score = float(item.get("score") or 0.0)
        if any(host == value or host.endswith("." + value) for value in _PRIMARY_HOSTS if not value.startswith(".")) or host.endswith(".gov"):
            score += 0.35
        if target_years and any(str(year) in text for year in target_years):
            score += 0.25
        mentioned = {int(value) for value in re.findall(r"\b20\d{2}\b", text)}
        if target_years and mentioned and not (mentioned & target_years):
            score -= 0.3
        if any(marker in text for marker in _WEAK):
            score -= 0.2
        item["registered_domain"] = domain
        item["source_priority"] = round(score, 4)
        scored.append((score, index, item))
    scored.sort(key=lambda value: (-value[0], value[1]))
    first: list[dict[str, Any]] = []
    later: list[dict[str, Any]] = []
    seen: set[str] = set()
    for _score, _index, item in scored:
        domain = str(item["registered_domain"])
        (later if domain in seen else first).append(item)
        seen.add(domain)
    return [*first, *later]
