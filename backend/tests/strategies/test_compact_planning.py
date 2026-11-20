import json

import pytest

from deeptrace.domain import ResearchMode
from strategies.test_minimal_planning_contract import run_planner, PLANNERS, QUESTION


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', list(ResearchMode))
async def test_canonical_task_can_reference_declared_delivery_criteria_without_creating_gaps(mode):
    result, _, _ = await run_planner(mode, 2, json.dumps({
        'requirements': [{'id':'r1','description':'External retry rule','kind':'fact'},
                         {'id':'r2','description':'Design bounded backoff','kind':'design_criterion'}],
        'tasks': [{'id':'t1','query':'retry rule','requirement_ids':['r1','r2'],'read_terms':['Retry-After']}],
    }))
    assert not result['decomposition_degraded']
    assert result['query_targets'] == {'retry rule':['r1']}
    assert len(result['requirements']) == 1
    assert 'Design bounded backoff' in result['research_brief']['answer_criteria']


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', list(ResearchMode))
async def test_canonical_tasks_dispatch_without_repair_or_scope_loss(mode):
    result, _, _ = await run_planner(mode, 3, json.dumps({
        'requirements': [{'id': 'r1', 'description': 'Alpha release date'},
                         {'id': 'r2', 'description': 'Beta license'}],
        'tasks': [
            {'id': 't1', 'query': 'Alpha release', 'requirement_ids': ['r1'],
             'read_terms': ['release date']},
            {'id': 't2', 'query': 'Beta license', 'requirement_ids': ['r2'],
             'read_terms': ['license terms']},
        ],
    }))
    assert result[PLANNERS[mode][3]] == ['Alpha release', 'Beta license']
    assert result['query_targets'] == {'Alpha release': ['r1'], 'Beta license': ['r2']}
    assert result['decomposition_degraded'] is False
    assert result['task_briefs']['Beta license']['read_terms'] == ['license terms']
    from deeptrace.strategies.model_io import branch_context
    assert branch_context({**result, 'question':QUESTION, 'query':'Beta license'})['read_terms'] == ['license terms']


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', list(ResearchMode))
async def test_invalid_canonical_task_never_drops_an_original_requirement(mode):
    result, _, _ = await run_planner(mode, 3, json.dumps({
        'requirements': [{'id': 'r1', 'description': 'Alpha'}],
        'tasks': [{'id': 't1', 'query': 'Alpha', 'requirement_ids': ['r9']}],
    }))
    assert result[PLANNERS[mode][3]] == [QUESTION]
    assert result['decomposition_degraded'] is True


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', list(ResearchMode))
async def test_many_valid_user_constraints_do_not_erase_canonical_decomposition(mode):
    result, _, _ = await run_planner(mode, 2, json.dumps({
        'requirements':[{'id':'r1','description':'Alpha release'}],
        'execution_constraints':['only supplied docs','30 seconds','3 attempts','stop when out of time',
            'preserve uncertainty','cite sections','answer in Chinese'],
        'tasks':[{'id':'t1','query':'Alpha release','requirement_ids':['r1'],'read_terms':[]}],
    }))
    assert result[PLANNERS[mode][3]] == ['Alpha release']
    assert result['decomposition_degraded'] is False
