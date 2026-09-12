"""Public module contracts for the Basic research implementation."""

import deeptrace.tools as tools_package
from deeptrace.basic.graph import build_research_graph
from deeptrace.basic.state import GraphState
from deeptrace.context import (
    CompressionRuntime,
    ContextCompressor,
    format_document_context,
)
from deeptrace.domain import ResearchMode
from deeptrace.harness import StrategyRegistry, build_agent_runtime_graph
from deeptrace.models import RawDocument, RunEvent, TokenUsage, UsageBreakdown
from deeptrace.multi_agent import SupervisorResearchAgent, build_multi_agent
from deeptrace.observability import estimate_usage_cost, format_role_usage
from deeptrace.prompts import build_planner_messages, build_writer_messages
from deeptrace.tools import ToolContext
from deeptrace.tools.scraper import AsyncWebFetcher, normalize_url_before_fetch
from deeptrace.tools.search import search_web


def test_foundation_packages_expose_basic_interfaces() -> None:
    assert RawDocument.__name__ == "RawDocument"
    assert RunEvent.__name__ == "RunEvent"
    assert TokenUsage.__name__ == "TokenUsage"
    assert UsageBreakdown.__name__ == "UsageBreakdown"


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


def test_multi_agent_is_a_peer_mode_with_its_own_public_entrypoints() -> None:
    assert SupervisorResearchAgent.__name__ == "SupervisorResearchAgent"
    assert callable(build_multi_agent)


def test_harness_foundation_interfaces_are_available() -> None:
    assert ResearchMode.WORKFLOW.value == "workflow"
    assert ResearchMode.PLAN_EXECUTE.value == "plan_execute"
    assert ResearchMode.MULTI_AGENT.value == "multi_agent"
    assert StrategyRegistry.__name__ == "StrategyRegistry"
    assert callable(build_agent_runtime_graph)


def test_prompts_and_tools_have_no_agent_loop_compatibility_exports() -> None:
    assert callable(build_planner_messages)
    assert callable(build_writer_messages)
    assert ToolContext.__name__ == "ToolContext"
    assert not hasattr(tools_package, "EXTERNAL_TOOL_SCHEMAS")
    assert not hasattr(tools_package, "RESEARCHER_TOOL_SCHEMAS")
