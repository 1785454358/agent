from tavily import TavilyClient

from deeptrace.config import Settings
from deeptrace.tools import ToolContext, search_web


def test_real_service_settings_are_available() -> None:
    settings = Settings.from_env()

    assert settings.openai_api_key
    assert settings.openai_base_url.startswith(("http://", "https://"))
    assert settings.openai_model
    assert settings.tavily_api_key
    assert 1 <= settings.max_steps <= 20
    assert 1_000 <= settings.max_page_chars <= 100_000


def test_search_web_calls_real_tavily_and_bounds_results() -> None:
    settings = Settings.from_env()
    context = ToolContext(
        tavily=TavilyClient(api_key=settings.tavily_api_key),
        http=None,
        max_page_chars=settings.max_page_chars,
    )

    result = search_web(
        context,
        query="Python official documentation",
        max_results=20,
    )

    assert result["ok"] is True
    assert result["query"] == "Python official documentation"
    assert 1 <= len(result["results"]) <= 5
    for item in result["results"]:
        assert item["title"]
        assert item["url"].startswith(("http://", "https://"))
        assert isinstance(item["snippet"], str)
