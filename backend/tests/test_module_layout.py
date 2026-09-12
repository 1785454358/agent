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
from deeptrace.tools import (
    AgentToolGateway,
    FetchPageArguments,
    SearchMemoryArguments,
    SearchWebArguments,
    ToolAdapterResult,
    ToolContext,
    build_research_tool_registry,
)
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
    assert not hasattr(tools_package, "ResearchToolbox")
    assert not hasattr(tools_package, "ResearcherTools")


def test_tools_expose_the_unified_gateway_and_atomic_adapter_contracts() -> None:
    assert AgentToolGateway.__name__ == "AgentToolGateway"
    assert ToolAdapterResult.__name__ == "ToolAdapterResult"
    assert SearchWebArguments.__name__ == "SearchWebArguments"
    assert FetchPageArguments.__name__ == "FetchPageArguments"
    assert SearchMemoryArguments.__name__ == "SearchMemoryArguments"
    assert callable(build_research_tool_registry)


def test_workflow_response_vertical_slice_public_contracts() -> None:
    from deeptrace.application import (
        ApplicationResearchRequest,
        ResearchApplicationService,
    )
    from deeptrace.domain import CitationRef, ResponseOutcome
    from deeptrace.harness import ResponseGraphRegistry, ResponseRegistration
    from deeptrace.responses import (
        build_answer_graph,
        build_brief_graph,
        build_report_graph,
    )
    from deeptrace.strategies import (
        build_multi_agent_research_graph,
        build_plan_execute_research_graph,
        build_workflow_research_graph,
    )

    assert callable(build_workflow_research_graph)
    assert callable(build_plan_execute_research_graph)
    assert callable(build_multi_agent_research_graph)
    assert callable(build_answer_graph)
    assert callable(build_brief_graph)
    assert callable(build_report_graph)
    assert CitationRef.__name__ == "CitationRef"
    assert ResponseOutcome.__name__ == "ResponseOutcome"
    assert ResponseGraphRegistry.__name__ == "ResponseGraphRegistry"
    assert ResponseRegistration.__name__ == "ResponseRegistration"
    assert ApplicationResearchRequest.__name__ == "ApplicationResearchRequest"
    assert ResearchApplicationService.__name__ == "ResearchApplicationService"
