from deeptrace.tools.scraper import extract_source_metadata


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
