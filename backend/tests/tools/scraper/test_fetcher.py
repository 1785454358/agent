from deeptrace.tools.scraper import (
    ExtractionCandidate,
    is_allowed_dns_resolution,
    is_usable_text,
    select_best_extraction,
)
from deeptrace.models import ScraperUsed
from deeptrace.tools.scraper.urls import validate_public_url


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


def test_benchmark_dns_proxy_requires_explicit_opt_in() -> None:
    """受控沙箱可放行域名代理地址，但字面量非公网 IP 始终被拒绝。"""
    assert not is_allowed_dns_resolution("198.18.0.12", False)
    assert is_allowed_dns_resolution("198.18.0.12", True)
    assert not is_allowed_dns_resolution("10.0.0.1", True)
    assert validate_public_url("https://198.18.0.12/news")[0] is False
