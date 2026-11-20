import json

import pytest
from langchain_core.messages import AIMessage
from deeptrace.domain import ResearchRequirement
from deeptrace.strategies.evidence_evaluation import run_evidence_evaluation
from deeptrace.strategies.workflow.models import ReferenceWorkflowEvaluation
from deeptrace.harness.checkpoint import create_harness_checkpoint_serializer
from strategies.fixtures import build_gateway_fixture
from strategies.test_strategy_reread import seed
from strategies.fixtures import evaluation_payload_from_view


class Assessor:
    evaluation_identity = {'model':'fixture', 'temperature':0}

    def __init__(self):
        self.calls = 0

    async def invoke(self, *, messages, **kwargs):
        self.calls += 1
        return AIMessage(content=json.dumps(evaluation_payload_from_view(str(messages[-1].content), sufficient=True)))


@pytest.mark.asyncio
async def test_verified_snapshot_reuses_after_checkpoint_but_changed_body_invalidates():
    model = Assessor()
    fixture = build_gateway_fixture(model_gateway=model)
    record = await seed(fixture, 1, 'Cancellation is cooperative. ' * 20)
    state = {'run_id':'run-1', 'thread_id':'thread-1', 'question':'Cancellation',
        'current_date':'2026-11-18', 'timezone':'Asia/Shanghai', 'evidence_contract_version':3,
        'requirements':[ResearchRequirement(id='r1',description='Cancellation')],
        'evidence_ids':[record.id]}
    first = await run_evidence_evaluation(state, fixture.context, ReferenceWorkflowEvaluation)
    count = model.calls
    serde = create_harness_checkpoint_serializer()
    restored = serde.loads_typed(serde.dumps_typed({**state, **first}))
    second = await run_evidence_evaluation(restored, fixture.context, ReferenceWorkflowEvaluation)
    assert model.calls == count
    assert second['coverage'] == first['coverage']
    await seed(fixture, 1, 'Earlier cancellation guarantee was withdrawn. ' * 20)
    await run_evidence_evaluation({**restored, **second}, fixture.context, ReferenceWorkflowEvaluation)
    assert model.calls == count + 1


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['question','run_id','requirements','model'])
async def test_snapshot_never_crosses_task_requirement_or_model_boundary(change):
    model = Assessor()
    fixture = build_gateway_fixture(model_gateway=model)
    record = await seed(fixture, 1, 'Cancellation is cooperative. ' * 20)
    state = {'run_id':'run-1', 'thread_id':'thread-1', 'question':'Cancellation',
        'current_date':'2026-11-18', 'timezone':'Asia/Shanghai', 'evidence_contract_version':3,
        'requirements':[ResearchRequirement(id='r1',description='Cancellation')],
        'evidence_ids':[record.id]}
    first = await run_evidence_evaluation(state, fixture.context, ReferenceWorkflowEvaluation)
    changed = {**state, **first}
    if change == 'model':
        model.evaluation_identity = {'model':'other', 'temperature':0}
    elif change == 'requirements':
        changed[change] = [ResearchRequirement(id='r1',description='Cancellation cleanup')]
    else:
        changed[change] = 'different'
    await run_evidence_evaluation(changed, fixture.context, ReferenceWorkflowEvaluation)
    assert model.calls == 2


@pytest.mark.asyncio
async def test_unknown_model_identity_disables_optional_cache_without_breaking_evaluation():
    model = Assessor()
    model.evaluation_identity = {'model': object()}
    fixture = build_gateway_fixture(model_gateway=model)
    record = await seed(fixture, 1, 'Cancellation is cooperative. ' * 20)
    state = {'run_id':'run-1','thread_id':'thread-1','question':'Cancellation',
        'current_date':'2026-11-18','timezone':'Asia/Shanghai','evidence_contract_version':3,
        'requirements':[ResearchRequirement(id='r1',description='Cancellation')],
        'evidence_ids':[record.id]}
    result = await run_evidence_evaluation(state, fixture.context, ReferenceWorkflowEvaluation)
    assert result['assessment'] is not None
    assert result['evaluation_snapshot'] is None
