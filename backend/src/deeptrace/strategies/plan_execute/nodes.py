"""Nodes for the Plan-and-Execute research strategy."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from pydantic import ValidationError

from deeptrace.domain import (
    ResearchInput,
    ResearchOutcome,
    ResearchMode,
    ResearchTopicInput,
    ResearchTopicOutcome,
)
from deeptrace.harness.context import HarnessContext
from deeptrace.strategies.model_io import parse_json_object, payload_text
from deeptrace.strategies.plan_execute.models import ExecutorDecision, TaskPlan
from deeptrace.strategies.workflow.nodes import filter_findings, topic_error_gaps
from deeptrace.strategies.plan_execute.state import PlanExecuteState


PLAN_EXECUTE_CALLER_ID = "plan-execute-executor"
PLANNER_ROLE = "planner"
REPLANNER_ROLE = "replanner"
EVALUATOR_ROLE = "evaluator"


def _research_input(state: PlanExecuteState) -> ResearchInput:
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


def build_plan_node(max_tasks: int):
    async def plan_node(
        state: PlanExecuteState, runtime: Runtime[HarnessContext]
    ) -> dict[str, Any]:
        research_input = _research_input(state)
        from deeptrace.strategies.model_io import conversation_background_lines

        background = conversation_background_lines(research_input)
        prompt = (
            "你是一次研究任务的规划器。请把用户问题拆解为互不重复的研究任务查询，"
            f"数量不超过 {max_tasks} 条，并只输出 JSON：{{\"queries\": [\"...\"]}}。\n\n"
            f"用户问题：{research_input.question}\n"
            + ("" if not background else "会话背景：\n" + "\n".join(background) + "\n")
            + f"今天日期：{research_input.current_date}"
        )
        queries: list[str] = []
        try:
            response = await runtime.context.model_gateway.invoke(
                role=PLANNER_ROLE, messages=[HumanMessage(content=prompt)]
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
            queries = []
        plan = TaskPlan(queries=queries or [research_input.question])
        return {
            "plan_tasks": plan.queries,
            "replan_count": 0,
            "executed_steps": 1,
        }

    return plan_node


def select_task_node(state: PlanExecuteState) -> dict[str, Any]:
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
        query = state["current_task"]
        topic_input = ResearchTopicInput(
            run_id=state["run_id"],
            thread_id=state["thread_id"],
            query=query,
            mode=ResearchMode.PLAN_EXECUTE,
            caller_id=PLAN_EXECUTE_CALLER_ID,
        )
        try:
            raw = await topic_graph.ainvoke(
                {"topic_input": topic_input}, config=config
            )
            outcome = ResearchTopicOutcome.model_validate(raw["outcome"])
        except Exception:
            return {
                "completed_tasks": [query],
                "executed_steps": 1,
                "unresolved_gaps": [f"topic_execution_failed:{query}"[:500]],
            }
        gaps = topic_error_gaps(outcome)
        updates: dict[str, Any] = {
            "completed_tasks": [query],
            "topic_outcomes": [outcome],
            "evidence_ids": list(outcome.evidence_ids),
            "executed_steps": outcome.executed_steps,
        }
        if gaps:
            updates["unresolved_gaps"] = gaps
        return updates

    return execute_task_node


async def evaluate_node(
    state: PlanExecuteState, runtime: Runtime[HarnessContext]
) -> dict[str, Any]:
    research_input = _research_input(state)
    evidence_ids = sorted(set(state.get("evidence_ids") or []))
    if not evidence_ids:
        return {
            "decision": None,
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
    completed = ", ".join(state.get("completed_tasks") or [])
    from deeptrace.strategies.model_io import conversation_background_lines

    background_lines = conversation_background_lines(research_input)[:6]
    prompt = (
        "你是一次研究任务的评估器。基于已执行任务与收集的资料，决定下一步动作。\n"
        "action 只能是 complete（资料足够）、replan（需要补充新查询）或 block（无法继续）。\n"
        "findings 中的 evidence_ids 必须逐字引用下方资料 ID。\n"
        '只输出 JSON：{"action", "reason", "findings": [{"id", "claim", "evidence_ids", "confidence"}], '
        '"unresolved_gaps": ["..."]}。\n\n'
        f"用户问题：{research_input.question}\n已完成任务：{completed}\n\n"
        + (
            ""
            if not background_lines
            else "会话背景：\n" + "\n".join(background_lines) + "\n\n"
        )
        + f"可用资料：\n{evidence_lines}"
    )
    try:
        response = await runtime.context.model_gateway.invoke(
            role=EVALUATOR_ROLE, messages=[HumanMessage(content=prompt)]
        )
        decision = ExecutorDecision.model_validate_json(payload_text(response))
    except (ValidationError, ValueError, TypeError):
        return {
            "decision": None,
            "findings": [],
            "unresolved_gaps": ["evaluation_unavailable"],
            "executed_steps": 1,
        }
    allowed = set(evidence_ids)
    findings = filter_findings(decision.findings, allowed_evidence_ids=allowed)
    return {
        "decision": decision,
        "findings": findings,
        "unresolved_gaps": list(decision.unresolved_gaps),
        "executed_steps": 1,
    }


def build_route_after_evaluate(max_replans: int):
    def route_after_evaluate(state: PlanExecuteState) -> str:
        decision = state.get("decision")
        if decision is None:
            return "finalize"
        if decision.action == "replan":
            if (state.get("replan_count") or 0) >= max_replans:
                return "finalize"
            return "replan"
        return "finalize"

    return route_after_evaluate


def build_replan_node(max_tasks: int):
    async def replan_node(
        state: PlanExecuteState, runtime: Runtime[HarnessContext]
    ) -> dict[str, Any]:
        research_input = _research_input(state)
        completed = state.get("completed_tasks") or []
        evidence_ids = sorted(set(state.get("evidence_ids") or []))
        prompt = (
            "你是一次研究任务的重规划器。已有资料仍不足以回答问题，"
            f"请提出最多 {max_tasks} 条全新的研究任务查询，"
            f"不得重复已完成任务：{', '.join(completed) or '（无）'}。\n"
            '只输出 JSON：{"queries": ["..."]}。\n\n'
            f"用户问题：{research_input.question}\n"
            f"已收集资料 ID：{', '.join(evidence_ids) or '（无）'}"
        )
        replan_count = (state.get("replan_count") or 0) + 1
        new_queries: list[str] = []
        try:
            response = await runtime.context.model_gateway.invoke(
                role=REPLANNER_ROLE, messages=[HumanMessage(content=prompt)]
            )
            payload = parse_json_object(payload_text(response))
            if payload is not None and isinstance(payload.get("queries"), list):
                for candidate in payload["queries"]:
                    if not isinstance(candidate, str):
                        continue
                    normalized = candidate.strip()
                    if not normalized or len(normalized) > 1000:
                        continue
                    if normalized not in completed and normalized not in new_queries:
                        new_queries.append(normalized)
                    if len(new_queries) >= max_tasks:
                        break
        except Exception:
            new_queries = []
        if new_queries:
            return {"plan_tasks": new_queries, "replan_count": replan_count}
        return {
            "plan_tasks": [],
            "replan_count": replan_count,
            "unresolved_gaps": ["no_new_tasks_to_plan"],
        }

    return replan_node


def route_after_replan(state: PlanExecuteState) -> str:
    if state.get("plan_tasks"):
        return "select_task"
    return "finalize"


def build_finalize_node(max_replans: int):
    def finalize_node(state: PlanExecuteState) -> dict[str, Any]:
        evidence_ids = sorted(set(state.get("evidence_ids") or []))
        decision = state.get("decision")
        gaps = list(dict.fromkeys(state.get("unresolved_gaps") or []))
        replan_count = state.get("replan_count") or 0
        if not evidence_ids:
            termination_reason = "no_sources"
        elif decision is not None and decision.action == "complete":
            termination_reason = "completed"
        elif decision is not None and decision.action == "replan":
            if replan_count >= max_replans or "no_new_tasks_to_plan" in gaps:
                termination_reason = "max_replans_reached"
            else:
                termination_reason = "insufficient_evidence"
        else:
            termination_reason = "insufficient_evidence"
        outcome = ResearchOutcome(
            mode=ResearchMode.PLAN_EXECUTE,
            evidence_ids=evidence_ids,
            findings=list(state.get("findings") or []),
            unresolved_gaps=gaps,
            executed_steps=state.get("executed_steps") or 0,
            termination_reason=termination_reason,
        )
        return {"outcome": outcome}

    return finalize_node
