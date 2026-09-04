"""Web documents used by the Basic research pipeline."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel


class ScraperUsed(StrEnum):
    """最终提供正文的抓取及提取路径。"""

    SEARCH_PROVIDER = "search_provider"
    HTTPX_TRAFILATURA = "httpx_trafilatura"
    HTTPX_BS4 = "httpx_bs4"
    PLAYWRIGHT_TRAFILATURA = "playwright_trafilatura"
    PLAYWRIGHT_BS4 = "playwright_bs4"


class RawDocument(BaseModel):
    """A fetched page retained only for the duration of a research run."""

    doc_id: str
    requested_url: str
    final_url: str
    canonical_url: str | None
    title: str
    content: str
    content_hash: str
    fetched_at: datetime
    scraper_used: ScraperUsed
    status: Literal["success", "irrelevant", "failed"]
    error: str | None = None
    source_published_at: datetime | None = None
    source_modified_at: datetime | None = None
    publisher: str | None = None
