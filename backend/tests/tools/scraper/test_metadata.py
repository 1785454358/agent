from datetime import UTC, datetime

from deeptrace.tools.scraper import extract_source_metadata


def test_scholarly_citation_date_is_preserved_as_full_publication_date():
    metadata = extract_source_metadata('<meta name="citation_date" content="2026/09/29">')
    assert metadata.published_at == datetime(2026, 9, 29, tzinfo=UTC)


def test_json_ld_metadata_has_priority() -> None:
    html = """
    <meta property="article:published_time" content="2023-01-01T00:00:00Z">
    <script type="application/ld+json">
      {"@type":"Article","datePublished":"2024-04-05T08:00:00Z",
       "dateModified":"2024-04-06T09:00:00Z",
       "publisher":{"name":"Example Lab"}}
    </script>
    """
    value = extract_source_metadata(html)

    assert value.published_at.isoformat() == "2024-04-05T08:00:00+00:00"
    assert value.modified_at.isoformat() == "2024-04-06T09:00:00+00:00"
    assert value.publisher == "Example Lab"


def test_missing_metadata_stays_none() -> None:
    value = extract_source_metadata("<body>2024 overview</body>")

    assert value.published_at is None
    assert value.publisher is None


def test_arxiv_version_watermark_supplies_declared_date_without_guessing_from_identifier():
    metadata = extract_source_metadata('<div id="watermark-tr">arXiv:2501.12948v1 [cs.CL] 22 Jan 2025</div>')
    assert metadata.published_at == datetime(2025, 1, 22, tzinfo=UTC)
    assert extract_source_metadata('<main>arXiv:2501.12948</main>').published_at is None
