"""Nodes for the Multi-Agent research strategy."""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from langgraph.types import Send

from deeptrace.domain import (
    INCOMPLETE_PLAN_REASON,
    ResearchMode,
    ResearchOutcome,
    ResearchTopicInput,
    unfinished_plan_items,
)
from deeptrace.harness.context import HarnessContext
from deeptrace.strategies.common import (
    effective_termination_reason,
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
    branch_context,
    parent_evidence_candidates,
    parse_json_object,
    payload_text,
    research_messages,
)
from deeptrace.strategies.multi_agent.models import ReferenceSupervisorEvaluation
from deeptrace.strategies.multi_agent.state import (
    MultiAgentState,
    ResearcherBranchState,
)
from deeptrace.strategies.planning import planning_instruction

SUPERVISOR_ROLE = "supervisor"
EVALUATOR_ROLE = "evaluator"
FOLLOW_UP_ROLE = "follow_up"


def _queries_from_payload(response: Any, *, limit: int, exclude: set[str]) -> list[str]:
    payload = parse_json_object(payload_text(response))
    queries: list[str] = []
    if payload is None or not isinstance(payload.get("assignments"), list):
        return queries
    for candidate in payload["assignments"]:
        if not isinstance(candidate, str):
            continue
        normalized = candidate.strip()
        if not normalized or len(normalized) > 1000:
            continue
        if normalized in exclude or normalized in queries:
            continue
        queries.append(normalized)
        if len(queries) >= limit:
            break
    return queries


def build_supervisor_plan_node(max_researchers: int):
    async def supervisor_plan_node(
        state: MultiAgentState, runtime: Runtime[HarnessContext]
    ) -> dict[str, Any]:
        research_input = _research_input(state)
        from deeptrace.strategies.model_io import conversation_background_lines

        background = conversation_background_lines(research_input)
        prompt = (
            "你是一次研究的监督者。"
            + planning_instruction("assignments", max_researchers)
            + f"用户问题：{research_input.question}\n"
            + ("" if not background else "会话背景：\n" + "\n".join(background) + "\n")
            + f"今天日期：{research_input.current_date}"
        )
        assignments: list[str] = []
        payload = None
        try:
            response = await runtime.context.model_gateway.invoke(
                role=SUPERVISOR_ROLE, messages=research_messages(research_input, prompt)
            )
            assignments = _queries_from_payload(
                response, limit=max_researchers, exclude=set()
            )
            payload = parse_json_object(payload_text(response))
        except Exception:
            logging.getLogger(__name__).warning(
                "Research planning failed; using fallback", exc_info=True
            )
            assignments = []
        assignments, contract = seal_initial_plan(
            research_input.question, payload, assignments
        )
        return {
            **contract,
            "assignments": assignments,
            "round_number": 0,
            "executed_steps": 1,
        }

    return supervisor_plan_node


def route_researchers(state: MultiAgentState) -> list[Send]:
    require_evidence_contract(state)
    round_number = state.get("round_number") or 0
    return [
        Send(
            "researcher",
            ResearcherBranchState(
                run_id=state["run_id"],
                thread_id=state["thread_id"],
                query=query,
                prior_evidence_ids=parent_evidence_candidates(state),
                **branch_context(
                    {
                        **state,
                        "target_requirement_ids": assigned_targets(state, query),
                    }
                ),
                researcher_index=index,
                round_number=round_number,
            ),
        )
        for index, query in enumerate(state.get("assignments") or [])
    ]


def build_researcher_node(topic_graph):
    async def researcher_node(
        state: ResearcherBranchState,
        runtime: Runtime[HarnessContext],
        config: RunnableConfig,
    ) -> dict[str, Any]:
        require_evidence_contract(state)
        topic_input = ResearchTopicInput(
            run_id=state["run_id"],
            thread_id=state["thread_id"],
            query=state["query"],
            mode=ResearchMode.MULTI_AGENT,
            caller_id=f"researcher-{state['researcher_index']}",
            **await validated_branch_context(state, runtime.context),
        )
        try:
            outcome = await invoke_research_branch(topic_graph, topic_input, config)
        except Exception:
            logging.getLogger(__name__).warning(
                "Research branch failed; preserving partial outcome", exc_info=True
            )
            return {
                "executed_steps": 1,
                "dispatched_queries": [state["query"]],
                "diagnostic_gaps": [
                    f"researcher_execution_failed:{state['query']}"[:500]
                ],
            }
        gaps = topic_error_gaps(outcome)
        updates: dict[str, Any] = {
            "researcher_outcomes": [outcome],
            "evidence_ids": list(outcome.evidence_ids),
            "dispatched_queries": [state["query"]],
            "executed_steps": outcome.executed_steps,
        }
        if gaps:
            updates["diagnostic_gaps"] = gaps
        return updates

    return researcher_node


def aggregate_node(state: MultiAgentState) -> dict[str, Any]:
    # Researcher outputs already merged through reducers; aggregation only marks
    # the fan-in point so evaluation sees the full round result.
    return {}


async def supervisor_evaluate_node(
    state: MultiAgentState, runtime: Runtime[HarnessContext]
) -> dict[str, Any]:
    result = await run_evidence_evaluation(
        state,
        runtime.context,
        ReferenceSupervisorEvaluation,
        incomplete_action="follow_up",
    )
    return {"evaluation": result.pop("assessment"), **result}


def build_route_after_evaluate(max_follow_ups: int):
    def route_after_evaluate(state: MultiAgentState) -> str:
        if (
            strong_exit_reason(state)
            or state.get("no_progress")
            or coverage_complete(state)
        ):
            return "finalize"
        evaluation = state.get("evaluation")
        if evaluation is None and state.get("evidence_ids"):
            return "finalize"
        if evaluation is None or evaluation.action == "follow_up":
            if (state.get("round_number") or 0) >= max_follow_ups:
                return "finalize"
            return "follow_up"
        return "finalize"

    return route_after_evaluate


def build_follow_up_node(max_researchers: int):
    async def follow_up_node(
        state: MultiAgentState, runtime: Runtime[HarnessContext]
    ) -> dict[str, Any]:
        planned = await supplement_plan(
            state,
            runtime.context,
            role=FOLLOW_UP_ROLE,
            dispatched=state.get("dispatched_queries") or [],
            limit=max_researchers,
        )
        next_round = (state.get("round_number") or 0) + 1
        assignments = planned.pop("queries")
        if assignments:
            return {
                **planned,
                "assignments": assignments,
                "round_number": next_round,
            }
        return {
            **planned,
            "assignments": [],
            "round_number": next_round,
            "unresolved_gaps": [
                *(state.get("unresolved_gaps") or []),
                "no_new_assignments",
            ],
        }

    return follow_up_node


def route_after_follow_up(state: MultiAgentState) -> list[Send] | str:
    assignments = state.get("assignments") or []
    if not assignments:
        return "finalize"
    return route_researchers(state)


def build_finalize_node(max_follow_ups: int):
    def finalize_node(state: MultiAgentState) -> dict[str, Any]:
        requirements = require_evidence_contract(state)
        evidence_ids = sorted(set(state.get("evidence_ids") or []))
        evaluation = state.get("evaluation")
        from deeptrace.strategies.evidence_evaluation import final_evidence_gaps

        gaps = final_evidence_gaps(state)
        round_number = state.get("round_number") or 0
        unfinished = unfinished_plan_items(list(state.get("researcher_outcomes") or []))
        if strong_exit_reason(state):
            termination_reason = strong_exit_reason(state)
            gaps.append(f"agent_exit:{termination_reason}")
        elif state.get("no_progress"):
            termination_reason = "no_research_progress"
            gaps.append("no_research_progress")
        elif not evidence_ids:
            termination_reason = "no_sources"
        elif evaluation is not None and coverage_complete(state):
            termination_reason = INCOMPLETE_PLAN_REASON if unfinished else "completed"
        elif evaluation is not None and evaluation.action == "follow_up":
            if round_number >= max_follow_ups or "no_new_assignments" in gaps:
                termination_reason = "max_follow_ups_reached"
            else:
                termination_reason = "insufficient_evidence"
        else:
            termination_reason = "insufficient_evidence"
        termination_reason = effective_termination_reason(
            termination_reason, state.get("researcher_outcomes", [])
        )
        outcome = ResearchOutcome(
            source_eligibility=state.get("source_eligibility"),
            evidence_contract_version=3,
            requirements=requirements,
            coverage=state.get("coverage"),
            decomposition_degraded=state.get("decomposition_degraded", False),
            mode=ResearchMode.MULTI_AGENT,
            evidence_ids=evidence_ids,
            findings=list(state.get("findings") or []),
            unresolved_gaps=gaps,
            executed_steps=state.get("executed_steps") or 0,
            termination_reason=termination_reason,
        )
        return {"outcome": outcome}

    return finalize_node
