from dataclasses import replace

import httpx
from openai import OpenAI
from tavily import TavilyClient

from deeptrace.agent import ResearchAgent
from deeptrace.config import Settings
from deeptrace.tools import ToolContext


def _build_real_agent(settings: Settings) -> tuple[ResearchAgent, httpx.Client]:
    http_client = httpx.Client(
        timeout=15.0,
        follow_redirects=False,
        headers={"User-Agent": "DeepTrace-Stage01/0.1"},
    )
    context = ToolContext(
        tavily=TavilyClient(api_key=settings.tavily_api_key),
        http=http_client,
        max_page_chars=settings.max_page_chars,
    )
    model_client = OpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
    )
    return ResearchAgent(model_client, settings, context), http_client


def test_real_agent_uses_search_and_fetch_before_answering() -> None:
    settings = Settings.from_env()
    agent, http_client = _build_real_agent(settings)
    try:
        result = agent.run(
            "请先使用 search_web 搜索 Python 官方文档，再使用 "
            "fetch_webpage 阅读至少一个搜索结果，最后用中文概括 Python 是什么。"
        )
    finally:
        http_client.close()

    called_tools = [event.tool_name for event in result.tool_events]
    assert result.status == "completed"
    assert result.answer.strip()
    assert "search_web" in called_tools
    assert "fetch_webpage" in called_tools
    assert result.sources
    assert set(result.sources) == result.fetched_urls
    assert result.steps <= settings.max_steps

    serialized = repr(result)
    assert settings.openai_api_key not in serialized
    assert settings.tavily_api_key not in serialized


def test_real_agent_respects_one_step_budget() -> None:
    settings = replace(Settings.from_env(), max_steps=1)
    agent, http_client = _build_real_agent(settings)
    try:
        result = agent.run(
            "必须先调用 search_web 搜索 OpenAI 官方文档，然后才能回答。"
        )
    finally:
        http_client.close()

    assert result.status == "max_steps_reached"
    assert result.steps == 1
    assert len(result.tool_events) >= 1
