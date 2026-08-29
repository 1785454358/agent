import httpx
from tavily import TavilyClient

from deeptrace.config import Settings
from deeptrace.tools import (
    TOOL_SCHEMAS,
    ToolContext,
    execute_tool,
    fetch_webpage,
    search_web,
)


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


def test_fetch_webpage_reads_a_real_public_html_page() -> None:
    settings = Settings.from_env()
    with httpx.Client(
        timeout=15.0,
        follow_redirects=False,
        headers={"User-Agent": "DeepTrace-Stage01/0.1"},
    ) as client:
        context = ToolContext(
            tavily=TavilyClient(api_key=settings.tavily_api_key),
            http=client,
            max_page_chars=settings.max_page_chars,
        )
        result = fetch_webpage(context, "https://example.com/")

    assert result["ok"] is True
    assert result["url"] == "https://example.com/"
    assert "Example Domain" in result["content"]
    assert len(result["content"]) <= settings.max_page_chars
    assert result["url"] in context.fetched_urls


def test_fetch_webpage_rejects_localhost_and_explicit_private_ips() -> None:
    settings = Settings.from_env()
    context = ToolContext(
        tavily=TavilyClient(api_key=settings.tavily_api_key),
        http=None,
        max_page_chars=settings.max_page_chars,
    )

    for unsafe_url in (
        "http://localhost/admin",
        "http://127.0.0.1/",
        "http://10.0.0.1/",
        "http://169.254.169.254/latest/meta-data/",
        "file:///etc/passwd",
    ):
        result = fetch_webpage(context, unsafe_url)
        assert result["ok"] is False
        assert result["error"]["code"] == "unsafe_url"


def test_fetch_webpage_returns_a_structured_network_error() -> None:
    settings = Settings.from_env()
    with httpx.Client(timeout=5.0, follow_redirects=False) as client:
        context = ToolContext(
            tavily=TavilyClient(api_key=settings.tavily_api_key),
            http=client,
            max_page_chars=settings.max_page_chars,
        )
        result = fetch_webpage(context, "https://example.invalid/")

    assert result["ok"] is False
    assert result["error"]["code"] == "fetch_failed"


def test_tool_schemas_expose_exactly_two_tools() -> None:
    names = {item["function"]["name"] for item in TOOL_SCHEMAS}
    assert names == {"search_web", "fetch_webpage"}


def test_execute_tool_dispatches_a_real_search() -> None:
    settings = Settings.from_env()
    context = ToolContext(
        tavily=TavilyClient(api_key=settings.tavily_api_key),
        http=None,
        max_page_chars=settings.max_page_chars,
    )

    result = execute_tool(
        context,
        "search_web",
        {"query": "Tavily search API documentation", "max_results": 2},
    )

    assert result["ok"] is True
    assert 1 <= len(result["results"]) <= 2


def test_execute_tool_rejects_unknown_tool_without_network_access() -> None:
    settings = Settings.from_env()
    context = ToolContext(
        tavily=TavilyClient(api_key=settings.tavily_api_key),
        http=None,
        max_page_chars=settings.max_page_chars,
    )

    result = execute_tool(context, "delete_files", {})

    assert result["ok"] is False
    assert result["error"]["code"] == "unknown_tool"
