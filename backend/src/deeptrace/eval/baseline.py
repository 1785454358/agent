"""Fixed retrieval baseline; reuse the application's normal response pipeline."""

from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime

from deeptrace.domain import ResearchMode, ResearchOutcome, ToolName, ToolRequest
from deeptrace.harness.agent_tools import _urls_from_search_preview
from deeptrace.harness.context import HarnessContext
from deeptrace.tools.policy import (
    CallerRole,
    ToolCaller,
    UrlAuthorization,
    UrlAuthorizationSource,
)


class BaselineState(TypedDict, total=False):
    run_id: str
    thread_id: str
    question: str
    outcome: ResearchOutcome


def build_baseline_research_graph():
    async def retrieve(state: BaselineState, runtime: Runtime[HarnessContext]):
        context = runtime.context
        caller = ToolCaller(
            caller_id="workflow-graph",
            role=CallerRole.WORKFLOW_GRAPH,
            mode=ResearchMode.WORKFLOW,
        )
        steps = 0

        async def execute(tool, arguments, *, authorization=None):
            nonlocal steps
            steps += 1
            return await context.tool_gateway.execute(
                tenant_id=context.workspace_id,
                caller=caller,
                request=ToolRequest(
                    request_id="baseline-retrieval",
                    run_id=state["run_id"],
                    thread_id=state["thread_id"],
                    call_id=f"baseline-{steps}",
                    tool=tool,
                    arguments=arguments,
                ),
                authorization=authorization,
            )

        search = await execute(
            ToolName.SEARCH_WEB, {"query": state["question"], "limit": 5}
        )
        urls = _urls_from_search_preview(search.preview) if search.ok else []
        ids = []
        for url in urls[:3]:
            result = await execute(
                ToolName.FETCH_PAGE,
                {"url": url},
                authorization=UrlAuthorization(
                    source=UrlAuthorizationSource.AGENT_DISCOVERED, urls=frozenset(urls)
                ),
            )
            if result.ok:
                ids.extend(
                    evidence_id
                    for evidence_id in result.evidence_ids
                    if evidence_id not in ids
                )
        return {
            "outcome": ResearchOutcome(
                mode=ResearchMode.WORKFLOW,
                evidence_ids=ids,
                findings=[],
                unresolved_gaps=[] if ids else ["no_sources"],
                executed_steps=steps,
                termination_reason="completed" if ids else "no_sources",
            )
        }

    builder = StateGraph(BaselineState, context_schema=HarnessContext)
    builder.add_node("fixed_retrieval", retrieve)
    builder.add_edge(START, "fixed_retrieval")
    builder.add_edge("fixed_retrieval", END)
    return builder.compile()
