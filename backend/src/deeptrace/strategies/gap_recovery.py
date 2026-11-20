"""Shared read-before-search recovery for independent research strategies."""

from typing import Any, Mapping

from langgraph.runtime import Runtime

from deeptrace.domain import ResearchMode
from deeptrace.harness.context import HarnessContext
from deeptrace.strategies.evidence_evaluation import supplement_plan


async def recover_gaps(
    state: Mapping[str, Any], runtime: Runtime[HarnessContext], *, role: str,
    dispatched: list[str], limit: int, mode: ResearchMode, caller_id: str,
) -> dict[str, Any]:
    if state.get("recovery_read_pending") and state.get("recovery_queries"):
        # Revalidate deferred searches against the coverage produced by the
        # actual reread, without paying for another planning call or round.
        from deeptrace.strategies.workflow.recovery import prepare_search_node

        result = await prepare_search_node({**state, "queries": dispatched}, runtime)
        queries = result.pop("recovery_queries")
        return {**result, "queries": queries,
                "recovery_queries": [], "recovery_read_pending": False}

    plan = await supplement_plan(
        state, runtime.context, role=role, dispatched=dispatched, limit=limit,
        allow_reread=not state.get("reread_attempted", False),
    )
    if not plan.get("reread_actions"):
        return {**plan, "recovery_read_pending": False}
    from deeptrace.strategies.workflow.reread import reread_node

    result = await reread_node({**state, **plan}, runtime, mode=mode, caller_id=caller_id)
    if mode is ResearchMode.MULTI_AGENT:
        result["researcher_outcomes"] = result.pop("topic_outcomes", [])
    return {
        **plan, **result,
        "diagnostic_gaps": [*plan.get("diagnostic_gaps", []), *result.get("diagnostic_gaps", [])],
        "recovery_queries": plan["queries"], "queries": [], "recovery_read_pending": True,
    }
