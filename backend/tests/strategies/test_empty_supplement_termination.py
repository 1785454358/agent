from types import SimpleNamespace

import pytest

from deeptrace.domain import CoverageAssessment, ResearchRequirement
from deeptrace.strategies.plan_execute.nodes import build_finalize_node as finalize_plan
from deeptrace.strategies.multi_agent.nodes import build_finalize_node as finalize_multi


@pytest.mark.parametrize('mode', ['plan', 'multi'])
def test_empty_supplement_is_not_a_planning_limit(mode):
    state = dict(evidence_contract_version=3,
        requirements=[ResearchRequirement(id='r1', description='derive metric')],
        evidence_ids=['evidence-1'], findings=[],
        coverage=CoverageAssessment(items=[dict(requirement_id='r1', status='missing', reason='measurement absent')]))
    if mode == 'plan':
        state.update(decision=SimpleNamespace(action='replan'), replan_count=1,
                     unresolved_gaps=['no_new_tasks_to_plan'])
        result = finalize_plan(2)(state)
    else:
        state.update(evaluation=SimpleNamespace(action='follow_up'), round_number=1,
                     unresolved_gaps=['no_new_assignments'])
        result = finalize_multi(2)(state)
    assert result['outcome'].termination_reason == 'insufficient_evidence'
    assert result['outcome'].coverage.items[0].status == 'missing'


@pytest.mark.parametrize('mode', ['plan', 'multi'])
def test_real_exhausted_limit_still_reports_limit(mode):
    state = dict(evidence_contract_version=3,
        requirements=[ResearchRequirement(id='r1', description='derive metric')],
        evidence_ids=['evidence-1'], findings=[], unresolved_gaps=['measurement absent'],
        coverage=CoverageAssessment(items=[dict(requirement_id='r1', status='missing', reason='measurement absent')]))
    if mode == 'plan':
        state.update(decision=SimpleNamespace(action='replan'), replan_count=2)
        result = finalize_plan(2)(state)
        assert result['outcome'].termination_reason == 'max_replans_reached'
    else:
        state.update(evaluation=SimpleNamespace(action='follow_up'), round_number=2)
        result = finalize_multi(2)(state)
        assert result['outcome'].termination_reason == 'max_follow_ups_reached'
