from deeptrace.tools.scraper.urls import normalize_url_before_fetch


def test_normalize_url_removes_tracking_and_sorts_query() -> None:
    raw = "HTTPS://Example.COM/a/../news/?utm_source=x&b=2&a=1#top"

    assert normalize_url_before_fetch(raw) == "https://example.com/news?a=1&b=2"
