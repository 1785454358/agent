"""Recovery changes the selected solution without changing the user's contract."""

import copy
import json

import pytest
from langchain_core.messages import AIMessage

from research.test_solution_delivery import solution_payload
from research.test_runtime import request, recovery_fixture
from strategies.fixtures import build_gateway_fixture
from strategies.workflow.test_recovery import RecoveryModel
from deeptrace.harness.batch_research import build_batch_research_graph
from deeptrace.research.runtime import build_controller_research_graph
from deeptrace.strategies.evidence_evaluation import seal_initial_plan, supplement_plan


@pytest.mark.asyncio
@pytest.mark.parametrize('defect', [None, 'missing_requirement', 'unknown_finding', 'missing_reason'])
async def test_recovery_revises_solution_only_with_sealed_needs_and_accepted_basis(defect):
    data = solution_payload()
    _, sealed = seal_initial_plan('Plan a trip', data, data['queries'])
    from deeptrace.domain import CoverageAssessment, RequirementCoverage, Finding
    original = sealed['delivery_plan']
    revision = copy.deepcopy(data['delivery_plan'])
    revision['approach'] = 'Stay centrally and replace the unavailable excursion'
    payload = {'tasks': [], 'delivery_revision': {
        'plan': revision, 'reason': 'Accepted evidence excludes the original excursion',
        'finding_ids': ['f1'],
    }}
    if defect == 'missing_requirement':
        revision['evidence_needs'].pop()
    elif defect == 'unknown_finding':
        payload['delivery_revision']['finding_ids'] = ['invented']
    elif defect == 'missing_reason':
        payload['delivery_revision']['reason'] = ''
    class Model:
        async def invoke(self, **kwargs):
            return AIMessage(content=json.dumps(payload))
    state = {**request().model_dump(), **sealed,
        'findings': [Finding(id='f1', claim='Selected excursion is unavailable', evidence_ids=['e1'], confidence=1)],
        'coverage': CoverageAssessment(items=[RequirementCoverage(requirement_id=r.id, status='missing', reason='Missing')
                                               for r in sealed['requirements']])}
    from unittest.mock import Mock
    from types import SimpleNamespace
    state['verification'] = Mock(accepted_claims=[SimpleNamespace(id='f1')])
    result = await supplement_plan(state, build_gateway_fixture(model_gateway=Model()).context,
                                   role='replanner', dispatched=[], limit=2)
    if defect:
        assert 'delivery_plan' not in result
        assert 'delivery_revision_rejected' in result['diagnostic_gaps']
    else:
        assert result['delivery_plan'].approach == revision['approach']
        assert result['delivery_plan_history'][-1]['plan'] == original.model_dump(mode='json')
        assert result['delivery_plan_history'][-1]['reason'] == payload['delivery_revision']['reason']
        assert {n.requirement_id for n in result['delivery_plan'].evidence_needs} == {r.id for r in sealed['requirements']}
        assert all(item.status == 'missing' for item in result['coverage'].items)
        state['verification'].model_copy.assert_called_once_with(update={'coverage':result['coverage']})
    assert state['delivery_plan'] == original








def test_optional_unknown_expense_does_not_block_selected_budget_or_enter_total():
    from deeptrace.responses.budgets import BudgetTable, render_budget_content
    budget = BudgetTable.model_validate({'scope':'selected deployment', 'unit':'CNY/month', 'items':[
        {'label':'Selected resources', 'low':100, 'high':150, 'kind':'estimate'},
        {'label':'Optional domain', 'low':None, 'high':None, 'kind':'unpriced',
         'scope':'optional', 'note':'Not used by the selected local deployment'},
        {'label':'Optional paid relay', 'low':50, 'high':60, 'kind':'reference',
         'scope':'optional', 'note':'SMTP is already provided; this alternative is not selected'},
    ]})
    content, gaps = render_budget_content('{{budget_1}} Selected total {{total_1}}', [budget])
    assert not gaps
    assert 'Selected total 100—150' in content
    assert '可选' in content


def test_optional_expense_requires_explanation_of_exclusion():
    from deeptrace.responses.budgets import BudgetItem
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        BudgetItem(label='necessary cost', low=None, high=None, kind='unpriced', scope='optional')


@pytest.mark.asyncio
async def test_quota_failure_returns_an_actionable_blocker_without_search_or_more_model_calls():
    from harness.test_model_gateway import Provider
    from deeptrace.harness.model_gateway import ChatModelGateway
    from deeptrace.harness.model_budget import RunBudgetModelGateway
    from deeptrace.domain import ResponseInput, ResponseMode
    from deeptrace.responses.graph import build_answer_graph
    class QuotaError(RuntimeError):
        status_code = 429
        body = {'error': {'code':'credit_quota_exceeded'}}
    provider = Provider(QuotaError())
    gateway = RunBudgetModelGateway(ChatModelGateway(provider, retry_attempts=1))
    fixture = build_gateway_fixture(model_gateway=gateway)
    result = await build_controller_research_graph(build_batch_research_graph()).ainvoke(
        request().model_dump(), context=fixture.context)
    response = await build_answer_graph().ainvoke({'response_input':ResponseInput(
        question=request().question, response_mode=ResponseMode.ANSWER, research_outcome=result['outcome'],
    )}, context=fixture.context)
    assert provider.calls == 1
    assert fixture.search.calls == []
    assert result['outcome'].termination_reason == 'model_error'
    assert response['outcome'].partial_reason == 'model_quota_exhausted'
    assert '额度' in response['outcome'].content
    assert '恢复' in response['outcome'].content
