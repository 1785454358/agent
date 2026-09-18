"""Nodes for the Workflow research strategy."""

from __future__ import annotations

import json
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
from deeptrace.domain.evidence import Finding
from deeptrace.harness.context import HarnessContext
from deeptrace.strategies.model_io import parse_json_object, payload_text, branch_context, research_messages
from deeptrace.strategies.workflow.models import QueryPlan, WorkflowEvaluation
from deeptrace.strategies.workflow.state import TopicBranchState, WorkflowState


WORKFLOW_CALLER_ID = "workflow-graph"
PLANNER_ROLE = "planner"
EVALUATOR_ROLE = "evaluator"


def parse_query_plan(text: str, *, limit: int, fallback: str) -> list[str]:
    payload = parse_json_object(payload_text(text))
    queries: list[str] = []
    if payload is not None and isinstance(payload.get("queries"), list):
        for candidate in payload["queries"]:
            if not isinstance(candidate, str):
                continue
            normalized = candidate.strip()
            if not normalized or len(normalized) > 1000:
                continue
            if normalized not in queries:
                queries.append(normalized)
            if len(queries) >= limit:
                break
    return queries or [fallback]


def filter_findings(
    findings: list[Finding], *, allowed_evidence_ids: set[str]
) -> list[Finding]:
    return [
        finding
        for finding in findings
        if finding.evidence_ids and set(finding.evidence_ids) <= allowed_evidence_ids
    ]


def topic_error_gaps(outcome: ResearchTopicOutcome) -> list[str]:
    agent = outcome.agent_outcome
    extra = [f"agent_exit:{agent.stop_reason}"] if agent and agent.status != "completed" else []
    return extra + [
        f"topic[{outcome.query}] {error.stage}:{error.target}:{error.code}"
        for error in outcome.errors
    ]


def _research_input(state: WorkflowState) -> ResearchInput:
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


def build_plan_queries_node(query_limit: int):
    async def plan_queries_node(
        state: WorkflowState,
        runtime: Runtime[HarnessContext],
    ) -> dict[str, Any]:
        research_input = _research_input(state)
        from deeptrace.strategies.model_io import conversation_background_lines

        summary_lines = conversation_background_lines(research_input)
        prompt = (
            "你是一次研究任务的查询规划器。请基于用户问题生成互不重复的搜索查询，"
            f"数量不超过 {query_limit} 条，并只输出 JSON：{{\"queries\": [\"...\"]}}。\n\n"
            f"用户问题：{research_input.question}\n"
            + ("" if not summary_lines else "会话背景：\n" + "\n".join(summary_lines) + "\n")
            + f"今天日期：{research_input.current_date}"
        )
        queries: list[str]
        try:
            response = await runtime.context.model_gateway.invoke(
                role=PLANNER_ROLE, messages=research_messages(research_input, prompt)
            )
            queries = parse_query_plan(
                str(response), limit=query_limit, fallback=research_input.question
            )
        except Exception:
            queries = [research_input.question]
        return {"queries": queries, "executed_steps": 1}

    return plan_queries_node


def route_topics(state: WorkflowState) -> list[Send]:
    research_input = _research_input(state)
    queries = state.get("queries") or [research_input.question]
    return [
        Send(
            "research_topic",
            TopicBranchState(
                run_id=research_input.run_id,
                thread_id=research_input.thread_id,
                query=query,
                **branch_context(state),
            ),
        )
        for query in queries
    ]


def build_research_topic_node(topic_graph):
    async def research_topic_node(
        state: TopicBranchState,
        runtime: Runtime[HarnessContext],
        config: RunnableConfig,
    ) -> dict[str, Any]:
        topic_input = ResearchTopicInput(
            run_id=state["run_id"],
            thread_id=state["thread_id"],
            query=state["query"],
            mode=ResearchMode.WORKFLOW,
            caller_id=WORKFLOW_CALLER_ID,
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
        except Exception as exc:
            return {
                "executed_steps": 1,
                "unresolved_gaps": [
                    f"topic_execution_failed:{state['query']}:{type(exc).__name__}"[:500]
                ],
            }
        gaps = topic_error_gaps(outcome)
        updates: dict[str, Any] = {
            "topic_outcomes": [outcome],
            "evidence_ids": list(outcome.evidence_ids),
            "executed_steps": outcome.executed_steps,
        }
        if gaps:
            updates["unresolved_gaps"] = gaps
        return updates

    return research_topic_node


async def evaluate_node(
    state: WorkflowState,
    runtime: Runtime[HarnessContext],
) -> dict[str, Any]:
    research_input = _research_input(state)
    evidence_ids = sorted(set(state.get("evidence_ids") or []))
    if not evidence_ids:
        gaps = list(state.get("unresolved_gaps") or [])
        if "no_evidence_collected" not in gaps:
            gaps.append("no_evidence_collected")
        return {
            "evaluation": WorkflowEvaluation(
                findings=[], unresolved_gaps=[], sufficient=False
            ),
            "findings": [],
            "unresolved_gaps": gaps,
            "executed_steps": 1,
        }

    evidence_records = await runtime.context.evidence_store.get_many(
        runtime.context.workspace_id, evidence_ids
    )
    evidence_lines = "\n".join(
        f"- [{record.id}] {record.title} {record.canonical_url}"
        for record in evidence_records
    )
    topic_lines = "\n".join(
        f"- query: {outcome.query} | evidence: {len(outcome.evidence_ids)} | "
        f"errors: {[error.code for error in outcome.errors]}"
        for outcome in state.get("topic_outcomes") or []
    )
    prompt = (
        "你是一次研究任务的评估器。基于已收集资料判断是否足以回答用户问题。\n"
        "findings 中的 evidence_ids 必须逐字引用下方资料 ID，不得引用其他来源。\n"
        '只输出 JSON：{"findings": [{"id", "claim", "evidence_ids", "confidence"}], '
        '"unresolved_gaps": ["..."], "sufficient": true|false}。\n\n'
        f"用户问题：{research_input.question}\n\n已执行查询：\n{topic_lines}\n\n"
        f"可用资料：\n{evidence_lines}"
    )
    try:
        response = await runtime.context.model_gateway.invoke(
            role=EVALUATOR_ROLE, messages=research_messages(research_input, prompt)
        )
        evaluation = WorkflowEvaluation.model_validate_json(payload_text(response))
    except (ValidationError, ValueError, TypeError):
        return {
            "evaluation": WorkflowEvaluation(
                findings=[], unresolved_gaps=[], sufficient=False
            ),
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


def finalize_node(state: WorkflowState) -> dict[str, Any]:
    evidence_ids = sorted(set(state.get("evidence_ids") or []))
    evaluation = state.get("evaluation")
    gaps = list(dict.fromkeys(state.get("unresolved_gaps") or []))
    unfinished = unfinished_plan_items(list(state.get("topic_outcomes") or []))
    if not evidence_ids:
        termination_reason = "no_sources"
    elif evaluation is not None and evaluation.sufficient:
        termination_reason = (
            INCOMPLETE_PLAN_REASON if unfinished else "completed"
        )
    else:
        termination_reason = "insufficient_evidence"
    agent_results = [o.agent_outcome for o in state.get("topic_outcomes", []) if o.agent_outcome is not None]
    if termination_reason == "completed" and any(o.status != "completed" for o in agent_results):
        termination_reason = next(o.stop_reason for o in agent_results if o.status != "completed")
    outcome = ResearchOutcome(
        mode=ResearchMode.WORKFLOW,
        evidence_ids=evidence_ids,
        findings=list(state.get("findings") or []),
        unresolved_gaps=gaps,
        executed_steps=state.get("executed_steps") or 0,
        termination_reason=termination_reason,
    )
    return {"outcome": outcome}
