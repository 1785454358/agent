"""Nodes for the Plan-and-Execute research strategy."""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime

from deeptrace.domain import (
    INCOMPLETE_PLAN_REASON,
    ResearchMode,
    ResearchOutcome,
    ResearchTopicInput,
    unfinished_plan_items,
)
from deeptrace.harness.context import HarnessContext
from deeptrace.observability.progress import emit_progress
from deeptrace.strategies.common import (
    effective_termination_reason,
    filter_findings,  # noqa: F401 - public API re-export
    invoke_research_branch,
    strong_exit_reason,
    topic_error_gaps,
    validated_branch_context,
)
from deeptrace.strategies.common import (
    research_input_from_state as _research_input,
)
from deeptrace.strategies.evidence_evaluation import (
    coverage_complete,
    require_evidence_contract,
    run_evidence_evaluation,
    seal_initial_plan,
    supplement_plan,
)
from deeptrace.strategies.model_io import (
    assigned_targets,
    parse_json_object,
    payload_text,
    research_messages,
)
from deeptrace.strategies.plan_execute.models import ReferenceExecutorDecision, TaskPlan
from deeptrace.strategies.plan_execute.state import PlanExecuteState
from deeptrace.strategies.planning import planning_instruction

PLAN_EXECUTE_CALLER_ID = "plan-execute-executor"
PLANNER_ROLE = "planner"
REPLANNER_ROLE = "replanner"
EVALUATOR_ROLE = "evaluator"


def build_plan_node(max_tasks: int):
    async def plan_node(
        state: PlanExecuteState, runtime: Runtime[HarnessContext]
    ) -> dict[str, Any]:
        research_input = _research_input(state)
        await emit_progress(runtime.context, "planning.started", round=1)
        from deeptrace.strategies.model_io import conversation_background_lines

        background = conversation_background_lines(research_input)
        prompt = (
            "你是一次研究任务的规划器。"
            + planning_instruction("queries", max_tasks)
            + f"用户问题：{research_input.question}\n"
            + ("" if not background else "会话背景：\n" + "\n".join(background) + "\n")
            + f"今天日期：{research_input.current_date}"
        )
        queries: list[str] = []
        payload = None
        try:
            response = await runtime.context.model_gateway.invoke(
                role=PLANNER_ROLE, messages=research_messages(research_input, prompt)
            )
            payload = parse_json_object(payload_text(response))
            if payload is not None and isinstance(payload.get("queries"), list):
                for candidate in payload["queries"]:
                    if not isinstance(candidate, str):
                        continue
                    normalized = candidate.strip()
                    if not normalized or len(normalized) > 1000:
                        continue
                    if normalized not in queries:
                        queries.append(normalized)
                    if len(queries) >= max_tasks:
                        break
        except Exception:
            logging.getLogger(__name__).warning(
                "Research planning failed; using fallback", exc_info=True
            )
            queries = []
        queries, contract = seal_initial_plan(research_input.question, payload, queries)
        plan = TaskPlan(queries=queries, requirements=contract["requirements"])
        await emit_progress(
            runtime.context, "planning.completed", round=1,
            tasks_json=json.dumps(plan.queries, ensure_ascii=False),
        )
        return {
            **contract,
            "plan_tasks": plan.queries,
            "replan_count": 0,
            "executed_steps": 1,
        }

    return plan_node


def select_task_node(state: PlanExecuteState) -> dict[str, Any]:
    require_evidence_contract(state)
    remaining = list(state.get("plan_tasks") or [])
    if remaining:
        current = remaining.pop(0)
        return {"plan_tasks": remaining, "current_task": current}
    return {"current_task": None}


def route_after_select(state: PlanExecuteState) -> str:
    if state.get("current_task"):
        return "execute_task"
    return "evaluate"


def build_execute_task_node(topic_graph):
    async def execute_task_node(
        state: PlanExecuteState,
        runtime: Runtime[HarnessContext],
        config: RunnableConfig,
    ) -> dict[str, Any]:
        require_evidence_contract(state)
        query = state["current_task"]
        round_number = (state.get("replan_count") or 0) + 1
        await emit_progress(runtime.context, "task.started", round=round_number, task=query)
        branch = {
            **state,
            "target_requirement_ids": assigned_targets(state, query),
        }
        topic_input = ResearchTopicInput(
            run_id=state["run_id"],
            thread_id=state["thread_id"],
            query=query,
            mode=ResearchMode.PLAN_EXECUTE,
            caller_id=PLAN_EXECUTE_CALLER_ID,
            **await validated_branch_context(branch, runtime.context),
        )
        try:
            outcome = await invoke_research_branch(topic_graph, topic_input, config)
        except Exception:
            logging.getLogger(__name__).warning(
                "Research branch failed; preserving partial outcome", exc_info=True
            )
            await emit_progress(
                runtime.context, "task.failed", round=round_number,
                task=query, reason="topic_execution_failed",
            )
            return {
                "completed_tasks": [query],
                "executed_steps": 1,
                "diagnostic_gaps": [f"topic_execution_failed:{query}"[:500]],
            }
        gaps = topic_error_gaps(outcome)
        await emit_progress(
            runtime.context, "task.completed", round=round_number, task=query,
            reason=outcome.agent_outcome.stop_reason if outcome.agent_outcome else None,
        )
        updates: dict[str, Any] = {
            "completed_tasks": [query],
            "topic_outcomes": [outcome],
            "evidence_ids": list(outcome.evidence_ids),
            "executed_steps": outcome.executed_steps,
        }
        if gaps:
            updates["diagnostic_gaps"] = gaps
        return updates

    return execute_task_node


async def evaluate_node(
    state: PlanExecuteState, runtime: Runtime[HarnessContext]
) -> dict[str, Any]:
    round_number = (state.get("replan_count") or 0) + 1
    await emit_progress(runtime.context, "evaluation.started", round=round_number)
    result = await run_evidence_evaluation(
        state, runtime.context, ReferenceExecutorDecision,
        incomplete_action="replan", repair_attempts=1,
    )
    decision = result.pop("assessment")
    coverage = result.get("coverage")
    await emit_progress(
        runtime.context, "evaluation.completed", round=round_number,
        action=decision.action if decision else "unavailable",
        reason=decision.reason if decision else "evaluation_unavailable",
        gaps_json=json.dumps(result.get("unresolved_gaps") or [], ensure_ascii=False),
        covered=sum(item.status == "covered" for item in coverage.items) if coverage else 0,
        total=len(coverage.items) if coverage else 0,
    )
    return {"decision": decision, **result}


def build_evaluate_node(max_replans: int):
    async def evaluate_with_route(
        state: PlanExecuteState, runtime: Runtime[HarnessContext]
    ) -> dict[str, Any]:
        result = await evaluate_node(state, runtime)
        evaluated = {**state, **result}
        next_step = build_route_after_evaluate(max_replans)(evaluated)
        decision = result["decision"]
        reason = strong_exit_reason(evaluated)
        if not reason:
            if evaluated.get("no_progress"):
                reason = "no_research_progress"
            elif coverage_complete(evaluated):
                reason = "coverage_complete"
            elif next_step == "replan":
                reason = "insufficient_evidence"
            elif (state.get("replan_count") or 0) >= max_replans:
                reason = "max_replans_reached"
            else:
                reason = "evaluation_unavailable"
        await emit_progress(
            runtime.context, "research.route",
            round=(state.get("replan_count") or 0) + 1,
            action=decision.action if decision else "unavailable",
            next_step=next_step, reason=reason,
        )
        return result

    return evaluate_with_route


def build_route_after_evaluate(max_replans: int):
    def route_after_evaluate(state: PlanExecuteState) -> str:
        if (
            strong_exit_reason(state)
            or state.get("no_progress")
            or coverage_complete(state)
        ):
            return "finalize"
        decision = state.get("decision")
        if decision is None and state.get("evidence_ids"):
            return "finalize"
        if decision is None or decision.action == "replan":
            if (state.get("replan_count") or 0) >= max_replans:
                return "finalize"
            return "replan"
        return "finalize"

    return route_after_evaluate


def build_replan_node(max_tasks: int):
    async def replan_node(
        state: PlanExecuteState, runtime: Runtime[HarnessContext]
    ) -> dict[str, Any]:
        replan_count = (state.get("replan_count") or 0) + 1
        await emit_progress(
            runtime.context, "replanning.started", round=replan_count + 1,
            gaps_json=json.dumps(state.get("unresolved_gaps") or [], ensure_ascii=False),
        )
        planned = await supplement_plan(
            state,
            runtime.context,
            role=REPLANNER_ROLE,
            dispatched=state.get("completed_tasks") or [],
            limit=max_tasks,
        )
        new_queries = planned.pop("queries")
        await emit_progress(
            runtime.context, "replanning.completed", round=replan_count + 1,
            tasks_json=json.dumps(new_queries, ensure_ascii=False),
        )
        if new_queries:
            return {**planned, "plan_tasks": new_queries, "replan_count": replan_count}
        return {
            **planned,
            "plan_tasks": [],
            "replan_count": replan_count,
            "unresolved_gaps": [
                *(state.get("unresolved_gaps") or []),
                "no_new_tasks_to_plan",
            ],
        }

    return replan_node


def route_after_replan(state: PlanExecuteState) -> str:
    if state.get("plan_tasks"):
        return "select_task"
    return "finalize"


def build_finalize_node(max_replans: int):
    def finalize_node(state: PlanExecuteState) -> dict[str, Any]:
        requirements = require_evidence_contract(state)
        evidence_ids = sorted(set(state.get("evidence_ids") or []))
        decision = state.get("decision")
        from deeptrace.strategies.evidence_evaluation import final_evidence_gaps

        gaps = final_evidence_gaps(state)
        replan_count = state.get("replan_count") or 0
        unfinished = unfinished_plan_items(list(state.get("topic_outcomes") or []))
        if strong_exit_reason(state):
            termination_reason = strong_exit_reason(state)
            gaps.append(f"agent_exit:{termination_reason}")
        elif state.get("no_progress"):
            termination_reason = "no_research_progress"
            gaps.append("no_research_progress")
        elif not evidence_ids:
            termination_reason = "no_sources"
        elif decision is not None and coverage_complete(state):
            termination_reason = INCOMPLETE_PLAN_REASON if unfinished else "completed"
        elif decision is not None and decision.action == "replan":
            if replan_count >= max_replans or "no_new_tasks_to_plan" in gaps:
                termination_reason = "max_replans_reached"
            else:
                termination_reason = "insufficient_evidence"
        else:
            termination_reason = "insufficient_evidence"
        termination_reason = effective_termination_reason(
            termination_reason, state.get("topic_outcomes", [])
        )
        outcome = ResearchOutcome(
            source_eligibility=state.get("source_eligibility"),
            evidence_contract_version=3,
            requirements=requirements,
            coverage=state.get("coverage"),
            decomposition_degraded=state.get("decomposition_degraded", False),
            mode=ResearchMode.PLAN_EXECUTE,
            evidence_ids=evidence_ids,
            findings=list(state.get("findings") or []),
            unresolved_gaps=gaps,
            executed_steps=state.get("executed_steps") or 0,
            termination_reason=termination_reason,
        )
        return {"outcome": outcome}

    return finalize_node
