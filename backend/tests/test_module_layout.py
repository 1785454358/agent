"""Public module contracts for the Basic research implementation."""

from deeptrace.context import CompressionRuntime, ContextCompressor, format_document_context
from deeptrace.models import RawDocument, RunEvent, TokenUsage, UsageBreakdown
from deeptrace.observability import estimate_usage_cost, format_role_usage
from deeptrace.orchestration.graph import build_research_graph
from deeptrace.orchestration.state import GraphState
from deeptrace.prompts import build_planner_messages, build_writer_messages
import deeptrace.tools as tools_package
from deeptrace.tools import ToolContext
from deeptrace.tools.scraper import AsyncWebFetcher, normalize_url_before_fetch
from deeptrace.tools.search import search_web


def test_foundation_packages_expose_basic_interfaces() -> None:
    assert RawDocument.__name__ == "RawDocument"
    assert RunEvent.__name__ == "RunEvent"
    assert TokenUsage.__name__ == "TokenUsage"
    assert UsageBreakdown.__name__ == "UsageBreakdown"
    assert set(UsageBreakdown.model_fields) == {"planner", "writer"}


def test_context_and_web_interfaces_remain_available() -> None:
    assert CompressionRuntime.__name__ == "CompressionRuntime"
    assert ContextCompressor.__name__ == "ContextCompressor"
    assert callable(format_document_context)
    assert AsyncWebFetcher.__name__ == "AsyncWebFetcher"
    assert search_web.__name__ == "search_web"
    assert normalize_url_before_fetch("https://example.com/") == "https://example.com/"


def test_graph_and_observability_interfaces_are_basic_only() -> None:
    assert GraphState.__name__ == "GraphState"
    assert callable(build_research_graph)
    assert callable(estimate_usage_cost)
    assert callable(format_role_usage)


def test_prompts_and_tools_have_no_agent_loop_compatibility_exports() -> None:
    assert callable(build_planner_messages)
    assert callable(build_writer_messages)
    assert ToolContext.__name__ == "ToolContext"
    assert not hasattr(tools_package, "EXTERNAL_TOOL_SCHEMAS")
    assert not hasattr(tools_package, "RESEARCHER_TOOL_SCHEMAS")
