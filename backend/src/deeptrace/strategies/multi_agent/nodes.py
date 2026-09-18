"""Nodes for the Multi-Agent research strategy."""

from __future__ import annotations

from typing import Any
import asyncio

from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from langgraph.types import Send
from pydantic import ValidationError

from deeptrace.domain import (
    INCOMPLETE_PLAN_REASON,
    ResearchInput,
    ResearchOutcome,
    ResearchMode,
    ResearchTopicInput,
    ResearchTopicOutcome,
    unfinished_plan_items,
)
from deeptrace.harness.context import HarnessContext
from deeptrace.strategies.model_io import parse_json_object, payload_text, branch_context, research_messages
from deeptrace.strategies.multi_agent.models import SupervisorEvaluation
from deeptrace.strategies.multi_agent.state import (
    MultiAgentState,
    ResearcherBranchState,
)
from deeptrace.strategies.workflow.nodes import filter_findings, topic_error_gaps


SUPERVISOR_ROLE = "supervisor"
EVALUATOR_ROLE = "evaluator"
FOLLOW_UP_ROLE = "follow_up"


def _research_input(state: MultiAgentState) -> ResearchInput:
    return ResearchInput.model_validate(
        {
            "run_id": state["run_id"],
            "thread_id": state["thread_id"],
            "question": state["question"],
            "conversation_summary": state.get("conversation_summary") or {},
            "recent_messages": state.get("recent_messages") or [],
            "prior_evidence_ids": state.get("prior_evidence_ids") or [],
            "unresolved_gaps": [],
            "budget": state.get("budget") or {},
            "current_date": state["current_date"],
            "timezone": state["timezone"],
        }
    )


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
            "你是一次研究的监督者。请把用户问题拆解为互不重叠的研究方向，"
            f"最多 {max_researchers} 条，并只输出 JSON：{{\"assignments\": [\"...\"]}}。\n\n"
            f"用户问题：{research_input.question}\n"
            + ("" if not background else "会话背景：\n" + "\n".join(background) + "\n")
            + f"今天日期：{research_input.current_date}"
        )
        assignments: list[str] = []
        try:
            response = await runtime.context.model_gateway.invoke(
                role=SUPERVISOR_ROLE, messages=research_messages(research_input, prompt)
            )
            assignments = _queries_from_payload(
                response, limit=max_researchers, exclude=set()
            )
        except Exception:
            assignments = []
        if not assignments:
            assignments = [research_input.question]
        return {
            "assignments": assignments,
            "round_number": 0,
            "executed_steps": 1,
        }

    return supervisor_plan_node


def route_researchers(state: MultiAgentState) -> list[Send]:
    round_number = state.get("round_number") or 0
    return [
        Send(
            "researcher",
            ResearcherBranchState(
                run_id=state["run_id"],
                thread_id=state["thread_id"],
                query=query,
                **branch_context(state),
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
        topic_input = ResearchTopicInput(
            run_id=state["run_id"],
            thread_id=state["thread_id"],
            query=state["query"],
            mode=ResearchMode.MULTI_AGENT,
            caller_id=f"researcher-{state['researcher_index']}",
            original_task=state.get("original_task", state["query"]),
            constraints=state.get("constraints", []), context_notes=state.get("context_notes", []),
        )
        try:
            raw = await topic_graph.ainvoke(
                {"topic_input": topic_input}, config=config
            )
            outcome = ResearchTopicOutcome.model_validate(raw["outcome"])
            if outcome.agent_outcome and outcome.agent_outcome.status == "cancelled":
                raise asyncio.CancelledError()
        except Exception:
            return {
                "executed_steps": 1,
                "dispatched_queries": [state["query"]],
                "unresolved_gaps": [
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
            updates["unresolved_gaps"] = gaps
        return updates

    return researcher_node


def aggregate_node(state: MultiAgentState) -> dict[str, Any]:
    # Researcher outputs already merged through reducers; aggregation only marks
    # the fan-in point so evaluation sees the full round result.
    return {}


async def supervisor_evaluate_node(
    state: MultiAgentState, runtime: Runtime[HarnessContext]
) -> dict[str, Any]:
    research_input = _research_input(state)
    evidence_ids = sorted(set(state.get("evidence_ids") or []))
    if not evidence_ids:
        return {
            "evaluation": None,
            "findings": [],
            "unresolved_gaps": ["no_evidence_collected"],
            "executed_steps": 1,
        }

    evidence_records = await runtime.context.evidence_store.get_many(
        runtime.context.workspace_id, evidence_ids
    )
    evidence_lines = "\n".join(
        f"- [{record.id}] {record.title} {record.canonical_url}"
        for record in evidence_records
    )
    from deeptrace.strategies.model_io import conversation_background_lines

    background_lines = conversation_background_lines(research_input)[:6]
    prompt = (
        "你是一次多智能体研究的监督者。基于各研究员收集的资料，判断是否足够回答用户问题。\n"
        "action 只能是 complete（足够）或 follow_up（需要追加研究方向）。\n"
        "findings 中的 evidence_ids 必须逐字引用下方资料 ID。\n"
        '只输出 JSON：{"action", "reason", "findings": [{"id", "claim", "evidence_ids", "confidence"}], '
        '"unresolved_gaps": ["..."]}。\n\n'
        f"用户问题：{research_input.question}\n\n"
        + (
            ""
            if not background_lines
            else "会话背景：\n" + "\n".join(background_lines) + "\n\n"
        )
        + f"可用资料：\n{evidence_lines}"
    )
    try:
        response = await runtime.context.model_gateway.invoke(
            role=EVALUATOR_ROLE, messages=research_messages(research_input, prompt)
        )
        evaluation = SupervisorEvaluation.model_validate_json(
            payload_text(response)
        )
    except (ValidationError, ValueError, TypeError):
        return {
            "evaluation": None,
            "findings": [],
            "unresolved_gaps": ["evaluation_unavailable"],
            "executed_steps": 1,
        }
    allowed = set(evidence_ids)
    findings = filter_findings(evaluation.findings, allowed_evidence_ids=allowed)
    return {
        "evaluation": evaluation,
        "findings": findings,
        "unresolved_gaps": list(evaluation.unresolved_gaps),
        "executed_steps": 1,
    }


def build_route_after_evaluate(max_follow_ups: int):
    def route_after_evaluate(state: MultiAgentState) -> str:
        evaluation = state.get("evaluation")
        if evaluation is None:
            return "finalize"
        if evaluation.action == "follow_up":
            if (state.get("round_number") or 0) >= max_follow_ups:
                return "finalize"
            return "follow_up"
        return "finalize"

    return route_after_evaluate


def build_follow_up_node(max_researchers: int):
    async def follow_up_node(
        state: MultiAgentState, runtime: Runtime[HarnessContext]
    ) -> dict[str, Any]:
        research_input = _research_input(state)
        dispatched = set(state.get("dispatched_queries") or [])
        prompt = (
            "你是一次多智能体研究的监督者。现有资料仍不足以回答问题，"
            f"请提出最多 {max_researchers} 条全新的研究方向，"
            f"不得重复已派发的方向：{', '.join(sorted(dispatched)) or '（无）'}。\n"
            '只输出 JSON：{"assignments": ["..."]}。\n\n'
            f"用户问题：{research_input.question}"
        )
        next_round = (state.get("round_number") or 0) + 1
        assignments: list[str] = []
        try:
            response = await runtime.context.model_gateway.invoke(
                role=FOLLOW_UP_ROLE, messages=research_messages(research_input, prompt)
            )
            assignments = _queries_from_payload(
                response, limit=max_researchers, exclude=dispatched
            )
        except Exception:
            assignments = []
        if assignments:
            return {
                "assignments": assignments,
                "round_number": next_round,
            }
        return {
            "assignments": [],
            "round_number": next_round,
            "unresolved_gaps": ["no_new_assignments"],
        }

    return follow_up_node


def route_after_follow_up(state: MultiAgentState) -> list[Send] | str:
    assignments = state.get("assignments") or []
    if not assignments:
        return "finalize"
    round_number = state.get("round_number") or 0
    return [
        Send(
            "researcher",
            ResearcherBranchState(
                run_id=state["run_id"],
                thread_id=state["thread_id"],
                query=query,
                **branch_context(state),
                researcher_index=index,
                round_number=round_number,
            ),
        )
        for index, query in enumerate(assignments)
    ]


def build_finalize_node(max_follow_ups: int):
    def finalize_node(state: MultiAgentState) -> dict[str, Any]:
        evidence_ids = sorted(set(state.get("evidence_ids") or []))
        evaluation = state.get("evaluation")
        gaps = list(dict.fromkeys(state.get("unresolved_gaps") or []))
        round_number = state.get("round_number") or 0
        unfinished = unfinished_plan_items(
            list(state.get("researcher_outcomes") or [])
        )
        if not evidence_ids:
            termination_reason = "no_sources"
        elif evaluation is not None and evaluation.action == "complete":
            termination_reason = (
                INCOMPLETE_PLAN_REASON if unfinished else "completed"
            )
        elif evaluation is not None and evaluation.action == "follow_up":
            if round_number >= max_follow_ups or "no_new_assignments" in gaps:
                termination_reason = "max_follow_ups_reached"
            else:
                termination_reason = "insufficient_evidence"
        else:
            termination_reason = "insufficient_evidence"
        agent_results = [o.agent_outcome for o in state.get("researcher_outcomes", []) if o.agent_outcome is not None]
        if termination_reason == "completed" and any(o.status != "completed" for o in agent_results):
            termination_reason = next(o.stop_reason for o in agent_results if o.status != "completed")
        outcome = ResearchOutcome(
            mode=ResearchMode.MULTI_AGENT,
            evidence_ids=evidence_ids,
            findings=list(state.get("findings") or []),
            unresolved_gaps=gaps,
            executed_steps=state.get("executed_steps") or 0,
            termination_reason=termination_reason,
        )
        return {"outcome": outcome}

    return finalize_node
