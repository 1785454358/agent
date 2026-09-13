"""Public module contracts after the harness cutover."""

import deeptrace.tools as tools_package
from deeptrace.domain import ResearchMode
from deeptrace.harness import StrategyRegistry, build_agent_runtime_graph
from deeptrace.models import RawDocument, RunEvent, TokenUsage, UsageBreakdown
from deeptrace.tools import (
    AgentToolGateway,
    FetchPageArguments,
    SearchMemoryArguments,
    SearchWebArguments,
    ToolAdapterResult,
    build_research_tool_registry,
)
from deeptrace.tools.scraper import AsyncWebFetcher, normalize_url_before_fetch
from deeptrace.tools.search import search_web


def test_foundation_packages_expose_basic_interfaces() -> None:
    assert RawDocument.__name__ == "RawDocument"
    assert RunEvent.__name__ == "RunEvent"
    assert TokenUsage.__name__ == "TokenUsage"
    assert UsageBreakdown.__name__ == "UsageBreakdown"


def test_web_interfaces_remain_available() -> None:
    assert AsyncWebFetcher.__name__ == "AsyncWebFetcher"
    assert search_web.__name__ == "search_web"
    assert normalize_url_before_fetch("https://example.com/") == "https://example.com/"


def test_harness_interfaces_are_available() -> None:
    assert ResearchMode.WORKFLOW.value == "workflow"
    assert ResearchMode.PLAN_EXECUTE.value == "plan_execute"
    assert ResearchMode.MULTI_AGENT.value == "multi_agent"
    assert StrategyRegistry.__name__ == "StrategyRegistry"
    assert callable(build_agent_runtime_graph)


def test_tools_expose_the_unified_gateway_and_atomic_adapter_contracts() -> None:
    assert AgentToolGateway.__name__ == "AgentToolGateway"
    assert ToolAdapterResult.__name__ == "ToolAdapterResult"
    assert SearchWebArguments.__name__ == "SearchWebArguments"
    assert FetchPageArguments.__name__ == "FetchPageArguments"
    assert SearchMemoryArguments.__name__ == "SearchMemoryArguments"
    assert callable(build_research_tool_registry)


def test_legacy_orchestration_entry_points_are_removed() -> None:
    import deeptrace

    assert not hasattr(deeptrace, "build_real_agent")
    assert not hasattr(deeptrace, "build_basic_agent")
    assert not hasattr(deeptrace, "build_deep_agent")
    assert not hasattr(deeptrace, "build_multi_agent")


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
