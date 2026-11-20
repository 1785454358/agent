from deeptrace.tools.scraper.fetcher import AsyncWebFetcher


def test_observed_alternative_text_format_is_preserved_when_not_in_article_prose():
    html = '''<html><title>Specification</title><main>
    <p>Specification metadata and publication information.</p>
    <a href="/spec.txt">TXT</a><a href="/spec.html">HTML</a>
    <a href="https://other.example/unrelated.txt">TXT</a>
    </main></html>'''
    fetcher = AsyncWebFetcher()
    candidates = fetcher._extract_candidates(html, 'https://example.com/info/spec', browser=False)
    assert all('https://example.com/spec.txt' in row.text for row in candidates if row.text)
    assert all('https://other.example/unrelated.txt' not in row.text for row in candidates)
