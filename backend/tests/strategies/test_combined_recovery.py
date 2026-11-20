import pytest
from dataclasses import replace

from deeptrace.domain import CoverageAssessment, ResearchRequirement
from deeptrace.strategies.evidence_evaluation import supplement_plan
from deeptrace.strategies.workflow.models import ReferenceWorkflowEvaluation
from strategies.fixtures import build_gateway_fixture


def test_transport_nested_recovery_advice_moves_only_when_unambiguous():
    import json
    from deeptrace.strategies.evidence_references import parse_reference_evaluation
    result = parse_reference_evaluation(ReferenceWorkflowEvaluation, json.dumps({
        'sufficient':False, 'coverage':{'items':[{'requirement_id':'r1','status':'missing','reason':'unread'}],
            'recovery_tasks':[{'query':'original','target_requirement_ids':['r1']}]},
    }))
    assert result.recovery_tasks[0].query == 'original'


@pytest.mark.asyncio
async def test_evaluation_recovery_advice_replaces_planner_and_filters_covered_work():
    assessment = ReferenceWorkflowEvaluation.model_validate({
        'sufficient': False, 'coverage': {'items': [
            {'requirement_id':'r1', 'status':'covered', 'finding_ids':['f1'], 'reason':'supported'},
            {'requirement_id':'r2', 'status':'missing', 'reason':'need original text'},
        ]},
        'recovery_tasks': [
            {'query':'already searched', 'target_requirement_ids':['r2']},
            {'query':'specific original', 'target_requirement_ids':['r1','r2']},
        ],
    })
    class UnneededModel:
        async def invoke(self, **kwargs):
            pytest.fail('accepted evaluation advice must not trigger another planner')
    context = replace(build_gateway_fixture().context, model_gateway=UnneededModel())
    result = await supplement_plan({
        'run_id':'run-1', 'thread_id':'thread-1', 'question':'compare original text',
        'evidence_contract_version':3,
        'requirements':[ResearchRequirement(id='r1',description='first'),
                        ResearchRequirement(id='r2',description='second')],
        'coverage':assessment.coverage, 'evaluation':assessment,
    }, context, role='replanner', dispatched=['already searched'], limit=2)
    assert result['queries'] == ['specific original']
    assert result['supplement_targets'] == {'specific original':['r2']}
