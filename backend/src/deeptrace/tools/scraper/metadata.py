"""从 HTML 确定性提取来源发布元数据。"""

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from bs4 import BeautifulSoup


@dataclass(frozen=True, slots=True)
class SourceMetadata:
    published_at: datetime | None = None
    modified_at: datetime | None = None
    publisher: str | None = None
    source_type: str | None = None


def _datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip())
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except ValueError:
        try:
            return datetime.strptime(value.strip(), "%Y/%m/%d").replace(tzinfo=UTC)
        except ValueError:
            return None


def _objects(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from _objects(child)


def extract_source_metadata(html: str) -> SourceMetadata:
    """优先 JSON-LD，再读取 article/meta/time；失败字段保持 None。"""
    soup = BeautifulSoup(html, "html.parser")
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            payload = json.loads(script.string or script.get_text())
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        for item in _objects(payload):
            kinds = item.get("@type", [])
            kinds = [kinds] if isinstance(kinds, str) else kinds
            source_type = next((k for k in ("NewsArticle", "ScholarlyArticle", "Article") if isinstance(kinds, list) and k in kinds), None)
            published = _datetime(item.get("datePublished"))
            modified = _datetime(item.get("dateModified"))
            publisher = item.get("publisher")
            if isinstance(publisher, dict):
                publisher = publisher.get("name")
            if published or modified or publisher:
                return SourceMetadata(published, modified, str(publisher).strip() if publisher else None, source_type)
    def meta(names: tuple[str, ...]) -> str | None:
        for name in names:
            tag = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
            if tag and tag.get("content"):
                return str(tag["content"])
        return None
    published = _datetime(meta(("citation_publication_date", "citation_online_date", "citation_date",
                                "article:published_time", "datePublished", "date")))
    modified = _datetime(meta(("article:modified_time", "dateModified")))
    publisher = meta(("publisher", "article:publisher"))
    if published is None:
        watermark = soup.find(id="watermark-tr")
        stamp = re.fullmatch(r'arXiv:\s*\d{4}\.\d{4,5}v\d+\s*\[[^\]]+\]\s*(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})',
                             watermark.get_text(' ', strip=True)) if watermark else None
        if stamp:
            try:
                published = datetime.strptime(stamp[1], '%d %b %Y').replace(tzinfo=UTC)
            except ValueError:
                pass
    if published is None:
        time_tag = soup.find("time", attrs={"datetime": True})
        published = _datetime(time_tag.get("datetime")) if time_tag else None
    return SourceMetadata(published, modified, publisher)
