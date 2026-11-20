"""Initial research contracts and versioned gap plans, separate from execution."""

import json

from langgraph.runtime import Runtime
from langgraph.types import Overwrite

from deeptrace.domain import ResearchMode
from deeptrace.harness.context import HarnessContext
from deeptrace.research.adapters import build_contract_and_plan, build_discovery_tasks
from deeptrace.research.contract import ContractBudget
from deeptrace.research.state import ControllerState
from deeptrace.strategies.common import research_input_from_state
from deeptrace.strategies.workflow.nodes import build_plan_queries_node
from deeptrace.observability.progress import emit_progress


async def _contract_budget(context: HarnessContext) -> ContractBudget:
    gateway = context.model_gateway
    read_limits = getattr(gateway, "admission_limits", None)
    limits = await read_limits() if read_limits is not None else {}
    return ContractBudget(
        max_model_calls=limits.get("max_calls", getattr(gateway, "max_calls", 20)),
        max_input_tokens=limits.get("max_input_tokens", getattr(gateway, "max_input_tokens", 100_000)),
        max_seconds=limits.get("max_seconds", getattr(gateway, "max_seconds", 600)),
        finishing_calls=limits.get("finishing_calls", getattr(gateway, "finishing_calls", 3)),
    )


async def initialize_research(
    state: ControllerState, runtime: Runtime[HarnessContext], *,
    mode: ResearchMode, max_tasks: int,
) -> dict:
    await emit_progress(runtime.context, "planning.started", round=1, mode=mode.value)
    planner = build_plan_queries_node(max_tasks, preserve_queries=True)
    updates = await planner(state, runtime)
    delivery_discovery = None
    if updates.get("delivery_plan") is not None:
        from deeptrace.strategies.delivery_planning import discovery_from_delivery

        try:
            delivery_discovery = discovery_from_delivery(
                updates["delivery_plan"], updates["requirements"], limit=max_tasks,
            )
            updates.update(delivery_discovery)
        except ValueError:
            updates["diagnostic_gaps"].append("delivery_query_capacity_unassigned")
    brief = updates.get("research_brief") or {}
    contract, plan = build_contract_and_plan(
        run_id=state["run_id"], question=state["question"],
        requirements=updates["requirements"], queries=updates["queries"],
        query_targets=updates["query_targets"],
        source_policy=brief.get("source_policy", "general"),
        source_domains=brief.get("source_domains") or [],
        publication_years=brief.get("publication_years") or [],
        budget=await _contract_budget(runtime.context),
    )
    if delivery_discovery is not None:
        # Persist all seeds in the executable plan itself. Optional task briefs
        # must not be required to recover an assigned secondary fact query.
        plan = type(plan).model_validate({
            **plan.model_dump(),
            "tasks": [{**task.model_dump(), "query_seeds": delivery_discovery["task_briefs"][
                task.query_seeds[0]]["search_queries"]} for task in plan.tasks],
        })
    contract = type(contract).model_validate({
        **contract.model_dump(),
        "user_constraints": research_input_from_state(state).conversation_summary.user_constraints,
    })
    await emit_progress(runtime.context, "planning.completed", round=1, mode=mode.value,
                        tasks_json=json.dumps([task.objective for task in plan.tasks], ensure_ascii=False))
    return {
        **updates, "contract": contract, "plan": plan, "plan_history": [],
        "mode": mode.value, "round_count": 1,
        "task_results": Overwrite({}), "topic_outcomes": Overwrite([]),
        "evidence_ids": Overwrite([]),
        "diagnostic_gaps": Overwrite(updates.get("diagnostic_gaps") or []),
        "executed_steps": Overwrite(updates["executed_steps"]),
        "findings": [], "source_eligibility": {}, "verification": None,
        "evaluation": None, "outcome": None, "active_tasks": [],
        "task_modes": {}, "blocked_tasks": [],
        "field_actions": [], "field_checks": [], "field_reread_count": 0,
    }


def revise_research_plan(state: ControllerState) -> dict:
    """Append targeted work to successful tasks without creating a new contract."""
    old = state["plan"]
    queries = state.get("recovery_queries") or []
    offset = max(int(task.id[1:]) for plan in [*state["plan_history"], old] for task in plan.tasks)
    added = build_discovery_tasks(
        requirements=state["contract"].requirements, queries=queries,
        query_targets=state["supplement_targets"], first_task_number=offset + 1,
        source_policy=state["contract"].source_policy.mode,
    )
    retained = [task for task in old.tasks
                if (state.get("task_results") or {}).get(task.id, {}).get("status") == "completed"]
    if len(retained) + len(added) > 12:
        return {"recovery_queries": [], "diagnostic_gaps": ["plan_task_limit"]}
    plan = old.next_revision([*retained, *added], reason="Acquire evidence for verified coverage gaps")
    return {"plan": plan, "plan_history": [*state["plan_history"], old],
            "round_count": state["round_count"] + 1,
            "queries": list(dict.fromkeys([*state["queries"], *queries]))}
