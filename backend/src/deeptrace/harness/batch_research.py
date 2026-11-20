"""Checkpointed acquisition with direct scientific and supplement handoff."""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from deeptrace.domain import ResearchTopicOutcome
from deeptrace.harness.agent_state import AgentExecutorState, topic_input
from deeptrace.harness.batch_collection import (
    fetch_sources,
    read_sources,
    search_sources,
    stage_todos,
)
from deeptrace.harness.batch_synthesis import synthesize_findings
from deeptrace.harness.context import HarnessContext
from deeptrace.harness.policies.execution import ExecutionPolicy
from deeptrace.harness.source_selection import select_sources
from deeptrace.harness.token_budget import TokenBudgetConfig


class BatchResearchState(AgentExecutorState, total=False):
    candidate_urls: list[str]
    source_candidates: list[dict]
    batch_selected_ids: list[str]
    batch_read_previews: list[dict]
    batch_read_queries: dict[str, list[str]]
    synthesis_feedback: str
    synthesis_done: bool


def build_batch_research_graph(*, source_target=3, max_tool_concurrency=4,
                               token_budget=None, checkpointer=None):
    if not 1 <= source_target <= 8 or max_tool_concurrency < 1:
        raise ValueError("Invalid batch research limits")
    budget = token_budget or TokenBudgetConfig()

    async def search(state, runtime):
        return await search_sources(state, runtime.context)

    async def fetch(state, runtime):
        return await fetch_sources(state, runtime.context, source_target=source_target,
                                   concurrency=max_tool_concurrency)

    async def select(state, runtime):
        return await select_sources(state, runtime.context, budget)

    async def read(state, runtime):
        updates = await read_sources(state, runtime.context, concurrency=max_tool_concurrency)
        task = topic_input(state)
        if (
            (task.evidence_contract_version >= 3
             or task.source_policy == "research_results"
             or (task.research_gaps and task.target_requirement_ids))
            and updates.get("batch_read_previews")
            and not (updates.get("stop_reason") or state.get("stop_reason"))
        ):
            # The v3 parent evaluates these exact authorized read anchors.
            # Acquiring originals completes this branch, not global coverage;
            # another summary would add a smaller window and duplicate cost.
            updates["stop_reason"] = "completed"
        return updates

    async def synthesize(state, runtime):
        return await synthesize_findings(state, runtime.context, budget)

    def finalize(state):
        state = {**state, "todos": state.get("todos") or stage_todos(0),
                 "stop_reason": state.get("stop_reason") or "incomplete_plan"}
        agent = ExecutionPolicy(max_iterations=2).outcome(state)
        diagnostics = list(state.get("research_finding_diagnostics") or [])
        if not state.get("batch_read_previews") and agent.stop_reason == "incomplete_plan":
            diagnostics.append("batch_acquisition_incomplete")
        return {"outcome": ResearchTopicOutcome(
            query=topic_input(state).query, agent_outcome=agent, evidence_ids=agent.evidence_ids,
            attempted_urls=sorted(set(state.get("attempted_urls") or []))[:100],
            read_anchors=state.get("read_anchors") or [],
            read_anchor_diagnostics=state.get("read_anchor_diagnostics") or [],
            research_findings=state.get("research_findings") or [],
            research_finding_diagnostics=diagnostics,
            errors=(state.get("errors") or [])[-100:], executed_steps=agent.executed_steps,
            plan_total=agent.plan_total, plan_completed=agent.plan_completed,
            unfinished_todos=agent.unfinished_todos)}

    builder = StateGraph(BatchResearchState, context_schema=HarnessContext)
    for name, node in (("search", search), ("select_sources", select), ("fetch", fetch), ("read", read),
                       ("synthesize", synthesize), ("finalize", finalize)):
        builder.add_node(name, node)
    builder.add_edge(START, "search")
    builder.add_conditional_edges("search", lambda s: "finalize" if s.get("stop_reason") else "select_sources")
    builder.add_conditional_edges("select_sources", lambda s: "finalize" if s.get("stop_reason") else "fetch")
    builder.add_edge("fetch", "read")
    builder.add_conditional_edges("read", lambda s: "synthesize" if s.get("batch_read_previews") and not s.get("stop_reason") else "finalize")
    builder.add_conditional_edges("synthesize", lambda s: "finalize" if s.get("synthesis_done") or s.get("stop_reason") else "synthesize")
    builder.add_edge("finalize", END)
    return builder.compile(checkpointer=checkpointer)
