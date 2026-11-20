"""One Workflow recovery round using the shared sealed-gap planner."""

from langgraph.runtime import Runtime

from deeptrace.harness.context import HarnessContext
from deeptrace.observability.progress import emit_progress
from deeptrace.strategies.common import strong_exit_reason
from deeptrace.strategies.evidence_evaluation import (
    coverage_complete,
    current_source_records,
    parse_gap_tasks,
    progress_keys,
    require_evidence_contract,
    supplement_plan,
)
from deeptrace.strategies.workflow.state import WorkflowState


def route_after_evaluate(state: WorkflowState) -> str:
    if (
        not state.get("evaluation")
        or coverage_complete(state)
        or strong_exit_reason(state)
    ):
        return "finalize"
    if state.get("reread_attempted") and not state.get("recovery_search_dispatched"):
        return "prepare_search" if state.get("recovery_queries") else "recover"
    if state.get("recovery_attempted"):
        return "finalize"
    return "recover"


async def recover_node(
    state: WorkflowState,
    runtime: Runtime[HarnessContext],
) -> dict:
    updates = {"recovery_attempted": True, "recovery_queries": [], "executed_steps": 1}
    if getattr(runtime.context.model_gateway, "research_exhausted", False):
        return {**updates, "diagnostic_gaps": ["supplement_budget_exhausted"]}
    plan = await supplement_plan(
        state,
        runtime.context,
        role="replanner",
        dispatched=list(state.get("queries") or []),
        limit=2,
        allow_reread=not state.get("reread_attempted", False),
    )
    queries = plan.pop("queries")
    await emit_progress(
        runtime.context,
        "research.recovery.planned",
        queries=queries,
        target_requirement_ids=plan["supplement_targets"],
    )
    reads = plan.get("reread_actions") or []
    return {
        **plan,
        **updates,
        "recovery_queries": queries,
        "recovery_search_dispatched": not bool(reads),
    }


async def prepare_search_node(
    state: WorkflowState, runtime: Runtime[HarnessContext]
) -> dict:
    """Revalidate deferred targets after rereading; covered work never dispatches."""
    requirements = require_evidence_contract(state)
    coverage = state["coverage"]
    tasks = parse_gap_tasks(
        {
            "tasks": [
                {
                    "query": q,
                    "target_requirement_ids": (
                        state.get("supplement_targets") or {}
                    ).get(q, []),
                }
                for q in state.get("recovery_queries") or []
            ]
        },
        gap_ids={i.requirement_id for i in coverage.items if i.status != "covered"},
        requirement_ids={r.id for r in requirements},
        dispatched=list(state.get("queries") or []),
        limit=2,
    )
    if getattr(runtime.context.model_gateway, "research_exhausted", False):
        tasks = []
    records = await current_source_records(state, runtime.context)
    return {
        "recovery_queries": [t.query for t in tasks],
        "supplement_targets": {t.query: t.target_requirement_ids for t in tasks},
        "progress_before_supplement": sorted(
            progress_keys(records, state.get("findings") or [], coverage, source_eligibility=state.get("source_eligibility") or {})
        )[:256],
        "supplement_completed": False,
        "no_progress": False,
        "recovery_search_dispatched": True,
        "executed_steps": 1,
    }
