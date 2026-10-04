"""Nodes for the Workflow research strategy."""

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
    filter_findings,  # noqa: F401 - public API re-export used by existing callers
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
)
from deeptrace.strategies.model_io import (
    assigned_targets,
    branch_context,
    parent_evidence_candidates,
    parse_json_object,
    payload_text,
    research_messages,
)
from deeptrace.strategies.planning import planning_instruction
from deeptrace.strategies.workflow.models import ReferenceWorkflowEvaluation
from deeptrace.strategies.workflow.state import TopicBranchState, WorkflowState

WORKFLOW_CALLER_ID = "workflow-graph"
PLANNER_ROLE = "planner"
EVALUATOR_ROLE = "evaluator"
EVALUATION_REPAIR_MAX_CHARS = 4000


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


def build_plan_queries_node(query_limit: int):
    async def plan_queries_node(
        state: WorkflowState,
        runtime: Runtime[HarnessContext],
    ) -> dict[str, Any]:
        research_input = _research_input(state)
        from deeptrace.strategies.model_io import conversation_background_lines

        summary_lines = conversation_background_lines(research_input)
        prompt = (
            "你是一次研究任务的查询规划器。"
            + planning_instruction("queries", query_limit)
            + f"用户问题：{research_input.question}\n"
            + (
                ""
                if not summary_lines
                else "会话背景：\n" + "\n".join(summary_lines) + "\n"
            )
            + f"今天日期：{research_input.current_date}"
        )
        queries: list[str]
        payload = None
        try:
            response = await runtime.context.model_gateway.invoke(
                role=PLANNER_ROLE, messages=research_messages(research_input, prompt)
            )
            queries = parse_query_plan(
                payload_text(response),
                limit=query_limit,
                fallback=research_input.question,
            )
            payload = parse_json_object(payload_text(response))
        except Exception:
            logging.getLogger(__name__).warning(
                "Research planning failed; using fallback", exc_info=True
            )
            queries = [research_input.question]
        queries, contract = seal_initial_plan(research_input.question, payload, queries)
        return {**contract, "queries": queries, "executed_steps": 1}

    return plan_queries_node


def route_topics(state: WorkflowState) -> list[Send]:
    require_evidence_contract(state)
    research_input = _research_input(state)
    queries = state.get("queries") or [research_input.question]
    return [
        Send(
            "research_topic",
            TopicBranchState(
                run_id=research_input.run_id,
                thread_id=research_input.thread_id,
                query=query,
                prior_evidence_ids=parent_evidence_candidates(state),
                **branch_context({**state, "target_requirement_ids": assigned_targets(state, query)}),
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
        require_evidence_contract(state)
        topic_input = ResearchTopicInput(
            run_id=state["run_id"],
            thread_id=state["thread_id"],
            query=state["query"],
            mode=ResearchMode.WORKFLOW,
            caller_id=WORKFLOW_CALLER_ID,
            **await validated_branch_context(state, runtime.context),
        )
        try:
            outcome = await invoke_research_branch(topic_graph, topic_input, config)
        except Exception as exc:
            logging.getLogger(__name__).warning(
                "Research branch failed; preserving partial outcome", exc_info=True
            )
            return {
                "executed_steps": 1,
                "diagnostic_gaps": [
                    f"topic_execution_failed:{state['query']}:{type(exc).__name__}"[
                        :500
                    ]
                ],
            }
        gaps = topic_error_gaps(outcome)
        updates: dict[str, Any] = {
            "topic_outcomes": [outcome],
            "evidence_ids": list(outcome.evidence_ids),
            "executed_steps": outcome.executed_steps,
        }
        if gaps:
            updates["diagnostic_gaps"] = gaps
        return updates

    return research_topic_node


async def evaluate_node(
    state: WorkflowState, runtime: Runtime[HarnessContext]
) -> dict[str, Any]:
    result = await run_evidence_evaluation(
        state, runtime.context, ReferenceWorkflowEvaluation, repair_attempts=1
    )
    return {"evaluation": result.pop("assessment"), **result}


def finalize_node(state: WorkflowState) -> dict[str, Any]:
    requirements = require_evidence_contract(state)
    evidence_ids = sorted(set(state.get("evidence_ids") or []))
    evaluation = state.get("evaluation")
    from deeptrace.strategies.evidence_evaluation import final_evidence_gaps

    gaps = final_evidence_gaps(state)
    unfinished = unfinished_plan_items(list(state.get("topic_outcomes") or []))
    if strong_exit_reason(state):
        termination_reason = strong_exit_reason(state)
        gaps.append(f"agent_exit:{termination_reason}")
    elif not evidence_ids:
        termination_reason = "no_sources"
    elif evaluation is not None and evaluation.sufficient and coverage_complete(state):
        termination_reason = INCOMPLETE_PLAN_REASON if unfinished else "completed"
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
        mode=ResearchMode.WORKFLOW,
        evidence_ids=evidence_ids,
        findings=list(state.get("findings") or []),
        unresolved_gaps=gaps,
        executed_steps=state.get("executed_steps") or 0,
        termination_reason=termination_reason,
    )
    return {"outcome": outcome}
