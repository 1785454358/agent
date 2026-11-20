"""A transient read-only model retry is another admitted, charged dispatch."""

import pytest
from langgraph.runtime import Runtime
from strategies.fixtures import build_gateway_fixture
from strategies.workflow.test_graph import _research_input
from strategies.workflow.test_recovery import RecoveryModel

from deeptrace.domain import ErrorCategory
from deeptrace.harness.batch_research import build_batch_research_graph
from deeptrace.harness.model_budget import RunBudgetModelGateway
from deeptrace.harness.model_gateway import ModelCallError
from deeptrace.strategies.workflow.nodes import build_plan_queries_node
from harness.test_batch_research import BatchModel
from harness.test_reading_queries import task


class FlakyPlanner(RecoveryModel):
    def __init__(self, failures=1, category=ErrorCategory.TRANSIENT):
        super().__init__()
        self.failures, self.category, self.attempts = failures, category, 0

    async def invoke(self, *, role, messages, tools=None):
        self.attempts += 1
        if self.attempts <= self.failures:
            raise ModelCallError(self.category)
        return await super().invoke(role=role, messages=messages, tools=tools)


@pytest.mark.asyncio
async def test_planner_retry_preserves_valid_plan_and_charges_both_attempts():
    model = FlakyPlanner()
    budget = RunBudgetModelGateway(model, max_calls=5)
    fixture = build_gateway_fixture(model_gateway=budget)
    result = await build_plan_queries_node(3)(_research_input(), Runtime(context=fixture.context))
    assert result['evidence_contract_version'] == 3
    assert result['queries'] == ['initial official']
    assert model.attempts == budget.used_calls == 2


@pytest.mark.asyncio
async def test_retry_cannot_spend_reserved_finishing_calls():
    model = FlakyPlanner()
    budget = RunBudgetModelGateway(model, max_calls=3)
    fixture = build_gateway_fixture(model_gateway=budget)
    result = await build_plan_queries_node(3)(_research_input(), Runtime(context=fixture.context))
    assert model.attempts == budget.used_calls == 1
    assert result['decomposition_degraded'] is True


@pytest.mark.asyncio
@pytest.mark.parametrize('category,expected', [(ErrorCategory.TRANSIENT, 2), (ErrorCategory.FATAL, 1)])
async def test_repeated_failure_stops_and_fatal_failure_is_not_retried(category, expected):
    model = FlakyPlanner(failures=5, category=category)
    fixture = build_gateway_fixture(model_gateway=model)
    result = await build_plan_queries_node(3)(_research_input(), Runtime(context=fixture.context))
    assert model.attempts == expected
    assert result['decomposition_degraded'] is True


@pytest.mark.asyncio
async def test_source_selection_recovers_once_without_inventing_a_source():
    class FlakySelector(BatchModel):
        attempts = 0

        async def invoke(self, *, role, messages, tools=None):
            self.attempts += 1
            if self.attempts == 1:
                raise ModelCallError(ErrorCategory.TRANSIENT)
            return await super().invoke(role=role, messages=messages, tools=tools)

    model = FlakySelector()
    budget = RunBudgetModelGateway(model, max_calls=5)
    fixture = build_gateway_fixture(
        model_gateway=budget,
        default_search_results=[{'url': 'https://example.com/guide', 'title': 'Guide'}],
        pages={'https://example.com/guide': '长时间读取如何阻止清理：必须先释放读取事务。'},
    )
    result = await build_batch_research_graph().ainvoke({'topic_input': task()}, context=fixture.context)
    assert result['outcome'].read_anchors
    assert fixture.fetcher.calls == ['https://example.com/guide']
    assert model.attempts == budget.used_calls == 2
