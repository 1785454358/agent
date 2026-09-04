from datetime import UTC, datetime

import pytest

from deeptrace.models import RawDocument, ScraperUsed


@pytest.fixture
def raw_document() -> RawDocument:
    return RawDocument(
        doc_id="doc-01",
        requested_url="https://example.com/a",
        final_url="https://example.com/a",
        canonical_url="https://example.com/a",
        title="来源标题",
        content="整页正文唯一标记",
        content_hash="hash",
        fetched_at=datetime.now(UTC),
        scraper_used=ScraperUsed.HTTPX_TRAFILATURA,
        status="success",
    )
