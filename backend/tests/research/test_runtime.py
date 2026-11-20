"""Execution, bounded recovery and durable task results of the common runtime."""

import asyncio
from dataclasses import replace

import pytest
from strategies.fixtures import build_gateway_fixture

from deeptrace.domain import ConversationSummary, ResearchInput, ResearchMode, ResearchRequirement
from deeptrace.harness.batch_research import build_batch_research_graph
from deeptrace.research.adapters import build_contract_and_plan
from deeptrace.research.plan import ExecutionMode
from deeptrace.research.execution import execute_task as _execute_task
from deeptrace.research.runtime import build_controller_research_graph


def test_controller_graph_is_a_compiled_strategy_graph() -> None:
    executor = build_batch_research_graph()
    graph = build_controller_research_graph(executor)
    assert hasattr(graph, "ainvoke")


def request():
    return ResearchInput(
        run_id="run-1", thread_id="thread-1", question="Compare the evidence",
        current_date="2026-11-14", timezone="Asia/Shanghai",
        conversation_summary=ConversationSummary(
            user_constraints=["Use primary sources"], established_facts=["Previous result"]
        ),
        recent_messages=["Compare both methods"],
    )


def contract_plan():
    return build_contract_and_plan(
        run_id="run-1", question="Compare the evidence",
        requirements=[ResearchRequirement(id="r1", description="Compare methods")],
        queries=["method one"],
    )


class CaptureTopic:
    def __init__(self):
        self.requests = []

    async def ainvoke(self, data, config=None, **kwargs):
        task = data["topic_input"]
        self.requests.append(task)
        return {"outcome": {"query": task.query, "executed_steps": 1}}


@pytest.mark.asyncio
async def test_task_preserves_constraints_queries_mode_and_page_limit():
    from deeptrace.research.plan import TaskBudget
    contract, plan = contract_plan()
    task = plan.tasks[0].model_copy(update={
        "query_seeds": ("method one", "method two"), "budget": TaskBudget(max_calls=2, max_pages=2),
    })
    topic = CaptureTopic()
    context = build_gateway_fixture().context
    await _execute_task(
        task=task, contract=contract, research_input=request(), context=context,
        topic_graph=topic, authorized_evidence_ids=[], mode=ResearchMode.PLAN_EXECUTE,
    )
    received = topic.requests[0]
    assert received.constraints == ["Use primary sources"]
    assert "Previous result" in received.context_notes
    assert "Compare both methods" in received.context_notes
    assert received.search_queries == ["method one", "method two"]
    assert received.max_pages == 2
    assert received.mode == ResearchMode.PLAN_EXECUTE


@pytest.mark.asyncio
async def test_task_rejects_unimplemented_executor_before_calling_topic():
    contract, plan = contract_plan()
    task = plan.tasks[0].model_copy(update={"execution_hint": ExecutionMode.LOOP})
    topic = CaptureTopic()
    with pytest.raises(ValueError, match="unsupported.*executor"):
        await _execute_task(
            task=task, contract=contract, research_input=request(),
            context=build_gateway_fixture().context, topic_graph=topic,
            authorized_evidence_ids=[],
        )
    assert topic.requests == []


@pytest.mark.asyncio
async def test_task_model_limit_is_enforced_before_provider_dispatch():
    from deeptrace.harness.model_budget import ModelBudgetExceeded
    contract, plan = contract_plan()

    class Provider:
        calls = 0

        async def invoke(self, **kwargs):
            self.calls += 1

    class OverspendingTopic:
        async def ainvoke(self, data, config=None, *, context):
            for _ in range(3):
                await context.model_gateway.invoke(role="researcher", messages=[])
            return {"outcome": {"query": "method one"}}

    provider = Provider()
    context = replace(build_gateway_fixture().context, model_gateway=provider)
    with pytest.raises(ModelBudgetExceeded):
        await _execute_task(
            task=plan.tasks[0], contract=contract, research_input=request(),
            context=context, topic_graph=OverspendingTopic(), authorized_evidence_ids=[],
        )
    assert provider.calls == 2


def recovery_fixture(model):
    return build_gateway_fixture(
        model_gateway=model,
        search_results={
            "initial official": [{"url": "https://example.com/initial", "title": "Initial"}],
            "restart official": [{"url": "https://example.com/restart", "title": "Restart"}],
        },
        pages={
            "https://example.com/initial": "INITIAL_FACT: ordinary execution is documented.",
            "https://example.com/restart": "RECOVERY_FACT: restart requires durable storage.",
        },
    )












@pytest.mark.asyncio
async def test_contract_budget_restores_original_run_limits_before_planning():
    from harness.test_durable_model_budget import SnapshotStore, Provider, call
    from deeptrace.harness.model_budget import RunBudgetModelGateway
    from deeptrace.research.planning import _contract_budget
    store = SnapshotStore()
    original = RunBudgetModelGateway(Provider(), max_calls=10, max_input_tokens=70_000,
                                    max_seconds=200, run_id="run-1", store=store)
    await call(original)
    resumed = RunBudgetModelGateway(Provider(), max_calls=20, max_seconds=600,
                                   run_id="run-1", store=store)
    budget = await _contract_budget(replace(build_gateway_fixture().context, model_gateway=resumed))
    assert budget.max_model_calls == 10
    assert budget.max_input_tokens == 70_000
    assert budget.max_seconds == 200


def test_blank_response_cannot_complete_a_turn():
    from deeptrace.domain import ExecutionStatus, ResponseMode, ResponseOutcome
    from deeptrace.harness.graph import _finalize_turn
    from deeptrace.harness.state import new_turn
    turn = new_turn("run-1", "hello", ResearchMode.WORKFLOW)
    turn["requires_research"] = False
    response = ResponseOutcome(response_mode=ResponseMode.ANSWER, content="answer", partial_reason="no_evidence")
    response.content = " "  # Assignment is mutable; finalization must still fail closed.
    response.partial_reason = None
    turn["response_outcome"] = response
    assert _finalize_turn({"turn": turn})["turn"]["status"] == ExecutionStatus.PARTIAL






@pytest.mark.asyncio
async def test_task_preserves_planner_search_seeds():
    contract, plan = contract_plan()
    topic = CaptureTopic()
    await _execute_task(
        task=plan.tasks[0], contract=contract, research_input=request(),
        context=build_gateway_fixture().context, topic_graph=topic, authorized_evidence_ids=[],
        branch_state={"task_briefs": {"method one": {
            "search_queries": ["official method one", "original method two"]}}},
    )
    assert topic.requests[0].search_queries == ["official method one", "original method two"]
