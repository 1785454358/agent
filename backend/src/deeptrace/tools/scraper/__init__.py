"""网页抓取与 URL 处理公共接口。"""

from deeptrace.tools.scraper.fetcher import (
    AsyncWebFetcher,
    ExtractionCandidate,
    WebFetchError,
    is_allowed_dns_resolution,
    is_usable_text,
    select_best_extraction,
)
from deeptrace.tools.scraper.urls import (
    normalize_url_before_fetch,
    resolve_document_identity,
    validate_public_url,
)
from deeptrace.tools.scraper.metadata import SourceMetadata, extract_source_metadata

__all__ = [
    "AsyncWebFetcher",
    "ExtractionCandidate",
    "WebFetchError",
    "is_allowed_dns_resolution",
    "is_usable_text",
    "normalize_url_before_fetch",
    "resolve_document_identity",
    "select_best_extraction",
    "SourceMetadata",
    "extract_source_metadata",
    "validate_public_url",
]
