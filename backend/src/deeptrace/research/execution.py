"""Bounded research execution using the existing tool and run-budget boundaries."""

from __future__ import annotations

import asyncio
from dataclasses import replace

from deeptrace.domain import ResearchMode, ResearchTopicInput, ResearchTopicOutcome
from deeptrace.harness.model_budget import ModelBudgetExceeded
from deeptrace.harness.checkpoint import subgraph_config
from deeptrace.research.plan import ExecutionMode, TaskType
from deeptrace.strategies.common import validated_branch_context


class TaskModelGateway:
    """Bound one task attempt; the wrapped durable gateway owns total run usage."""

    def __init__(self, inner, max_calls: int):
        self.inner = inner
        self.max_calls = max_calls
        self.used_calls = 0
        self._lock = asyncio.Lock()

    @property
    def unavailable_reason(self):
        return getattr(self.inner, "unavailable_reason", None)

    @property
    def research_exhausted(self):
        # Reaching the local model cap does not forbid the already selected
        # fetch/read work. The shared run gateway still stops acquisition.
        return getattr(self.inner, "research_exhausted", False)

    async def invoke(self, **kwargs):
        async with self._lock:
            if self.used_calls >= self.max_calls:
                raise ModelBudgetExceeded("task_model_calls")
            self.used_calls += 1
        return await self.inner.invoke(**kwargs)


def require_supported_task(task, execution_mode):
    if task.type is not TaskType.DISCOVER or execution_mode is not ExecutionMode.RETRIEVE:
        raise ValueError(f"unsupported task executor: {task.type.value}/{execution_mode.value}")
    if not task.query_seeds or task.budget.max_pages < 1:
        raise ValueError("retrieve executor requires queries and a positive page budget")


async def execute_task(
    *, task, contract, research_input, context, topic_graph,
    authorized_evidence_ids, mode=ResearchMode.WORKFLOW, config=None,
    execution_mode=None, branch_state=None,
):
    execution_mode = execution_mode or (
        ExecutionMode.RETRIEVE if task.execution_hint is ExecutionMode.AUTO
        else task.execution_hint
    )
    require_supported_task(task, execution_mode)
    query = task.query_seeds[0]
    state = {
        **research_input.model_dump(),
        **(branch_state or {}),
        "query": query,
        "requirements": list(contract.requirements),
        "target_requirement_ids": list(task.requirement_ids),
        "prior_evidence_ids": list(authorized_evidence_ids),
        "evidence_ids": [],
        "evidence_contract_version": 3,
        "source_policy": contract.source_policy.mode,
        "source_domains": list(contract.source_policy.domains),
        "publication_years": list(contract.source_policy.publication_years),
    }
    fields = await validated_branch_context(state, context)
    fields["search_queries"] = fields["search_queries"] or list(task.query_seeds)
    fields["max_pages"] = min(fields["max_pages"], task.budget.max_pages)
    # Keep existing caller scopes so durable tool budgets remain compatible.
    caller = caller_for_mode(mode)
    request = ResearchTopicInput(
        run_id=research_input.run_id, thread_id=research_input.thread_id,
        query=query, mode=mode, caller_id=caller, **fields,
    )
    bounded = replace(context, model_gateway=TaskModelGateway(context.model_gateway, task.budget.max_calls))
    raw = await topic_graph.ainvoke({"topic_input": request}, config=subgraph_config(config), context=bounded)
    outcome = ResearchTopicOutcome.model_validate(raw["outcome"])
    if outcome.query != query:
        raise ValueError("executor returned a result for another query")
    if outcome.agent_outcome and outcome.agent_outcome.status == "cancelled":
        raise asyncio.CancelledError()
    return outcome


def caller_for_mode(mode: ResearchMode) -> str:
    return {
        ResearchMode.WORKFLOW: "workflow-graph",
        ResearchMode.PLAN_EXECUTE: "plan-execute-executor",
        ResearchMode.MULTI_AGENT: "researcher-0",
    }[mode]
