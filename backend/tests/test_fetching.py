from deeptrace.fetching import ExtractionCandidate, is_usable_text, select_best_extraction
from deeptrace.models import ScraperUsed


def test_text_must_pass_both_quality_minimums() -> None:
    assert not is_usable_text("字" * 600, lambda _: 150, 500, 200)
    assert is_usable_text("字" * 600, lambda _: 220, 500, 200)


def test_fallback_selects_best_text_and_records_its_scraper() -> None:
    candidates = [
        ExtractionCandidate(
            text="短" * 300,
            title="HTTPX Trafilatura",
            scraper_used=ScraperUsed.HTTPX_TRAFILATURA,
            source_url="https://example.com/news",
        ),
        ExtractionCandidate(
            text="长" * 700,
            title="Playwright BS4",
            scraper_used=ScraperUsed.PLAYWRIGHT_BS4,
            source_url="https://example.com/news",
        ),
    ]

    selected = select_best_extraction(candidates)

    assert selected.text == "长" * 700
    assert selected.scraper_used is ScraperUsed.PLAYWRIGHT_BS4
