"""Assemble a production-shaped harness runtime from application settings."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from langchain_openai import ChatOpenAI
from tavily import TavilyClient

from deeptrace.application.research import ResearchApplicationService
from deeptrace.config import Settings
from deeptrace.domain import ResearchMode, ResponseMode
from deeptrace.harness.context import HarnessContext
from deeptrace.harness.graph import build_agent_runtime_graph
from deeptrace.harness.model_gateway import ChatModelGateway
from deeptrace.harness.registry import (
    ResponseGraphRegistry,
    ResponseRegistration,
    StrategyRegistration,
    StrategyRegistry,
)
from deeptrace.observability.events import HarnessEventRecorder
from deeptrace.responses import (
    build_answer_graph,
    build_brief_graph,
    build_report_graph,
)
from deeptrace.strategies import (
    build_multi_agent_research_graph,
    build_plan_execute_research_graph,
    build_research_topic_graph,
    build_workflow_research_graph,
)
from deeptrace.tools import AgentToolGateway, build_research_tool_registry
from deeptrace.tools.budget import (
    BudgetScopeKey,
    BudgetUnits,
    InMemoryBudgetManager,
)
from deeptrace.tools.cache import InMemorySuccessCache, SuccessCacheSingleflight
from deeptrace.tools.evidence_store import InMemoryEvidenceStore
from deeptrace.tools.execution_store import InMemoryToolExecutionStore
from deeptrace.tools.policy import (
    DeterministicUrlSecurityPolicy,
    StaticToolAllowlist,
)
from deeptrace.tools.search import ToolContext
from deeptrace.tools.search.tavily import search_web
from deeptrace.tools.scraper import AsyncWebFetcher


def _budgets_for_run(run_id: str) -> InMemoryBudgetManager:
    limit = BudgetUnits(tool_calls=60, network_requests=90, fetched_pages=60)
    scopes: list[BudgetScopeKey] = [BudgetScopeKey.for_run(run_id)]
    for mode in ResearchMode:
        scopes.append(BudgetScopeKey.for_mode(run_id, mode))
        for caller in ("workflow-graph", "plan-execute-executor"):
            scopes.append(BudgetScopeKey.for_agent(run_id, mode, caller))
        for index in range(6):
            scopes.append(
                BudgetScopeKey.for_agent(run_id, mode, f"researcher-{index}")
            )
    return InMemoryBudgetManager({scope: limit for scope in scopes})


def build_harness_runtime(
    settings: Settings,
) -> tuple[ResearchApplicationService, Callable[[str], HarnessContext]]:
    """Assemble the top-level runtime graph plus a per-run context factory.

    ``context_factory(run_id)`` builds the runtime dependencies for one run:
    page bodies live only in the Evidence Store; budgets, the execution ledger
    and caches are process-local (MySQL-backed adapters slot in behind the same
    ports in Plan 7's persistence layer).
    """
    model = ChatOpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        model=settings.openai_model,
        temperature=0,
        max_tokens=settings.openai_max_tokens,
    )
    model_gateway = ChatModelGateway(model)

    fetcher = AsyncWebFetcher(
        min_chars=settings.min_extracted_chars,
        min_tokens=settings.min_extracted_tokens,
        max_page_chars=settings.max_page_chars,
        allow_benchmark_dns_proxy=settings.allow_benchmark_dns_proxy,
    )

    strategies = StrategyRegistry()
    topic = build_research_topic_graph()
    strategies.register(
        StrategyRegistration(
            ResearchMode.WORKFLOW, build_workflow_research_graph(topic)
        )
    )
    strategies.register(
        StrategyRegistration(
            ResearchMode.PLAN_EXECUTE, build_plan_execute_research_graph(topic)
        )
    )
    strategies.register(
        StrategyRegistration(
            ResearchMode.MULTI_AGENT, build_multi_agent_research_graph(topic)
        )
    )
    responses = ResponseGraphRegistry()
    responses.register(
        ResponseRegistration(ResponseMode.ANSWER, build_answer_graph())
    )
    responses.register(
        ResponseRegistration(ResponseMode.BRIEF, build_brief_graph())
    )
    responses.register(
        ResponseRegistration(ResponseMode.REPORT, build_report_graph())
    )
    graph = build_agent_runtime_graph(strategies, responses)
    service = ResearchApplicationService(graph)

    def context_factory(run_id: str) -> HarnessContext:
        evidence_store = InMemoryEvidenceStore()
        recorder = HarnessEventRecorder(run_id=run_id)
        tool_context = ToolContext(
            tavily=TavilyClient(api_key=settings.tavily_api_key)
        )

        def run_search(query: str) -> Any:
            return search_web(tool_context, query, max_results=5)

        registry = build_research_tool_registry(search=run_search, fetcher=fetcher)
        tool_gateway = AgentToolGateway(
            registry=registry,
            allowlist=StaticToolAllowlist(),
            security=DeterministicUrlSecurityPolicy(),
            budgets=_budgets_for_run(run_id),
            executions=InMemoryToolExecutionStore(),
            cache=SuccessCacheSingleflight(InMemorySuccessCache()),
            evidence_store=evidence_store,
            event_sink=recorder,
        )
        return HarnessContext(
            user_id="local-user",
            workspace_id="local-workspace",
            model_gateway=model_gateway,
            tool_gateway=tool_gateway,
            evidence_store=evidence_store,
            event_sink=recorder,
            clock=_SystemClock(),
        )

    return service, context_factory


class _SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)
