"""Small-sample statistics never manufacture results from blocked trials."""

import pytest

from deeptrace.evaluation.local_sample import build_cases, summarize


def test_eight_cases_cover_six_categories_without_leaking_reference_answers():
    cases = build_cases()
    assert len(cases) == len({c['metadata']['id'] for c in cases}) == 8
    assert len({c['metadata']['category'] for c in cases}) == 6
    assert all(set(c['inputs']) == {'question','documents'} for c in cases)
    assert all(len(c['inputs']['documents']) == 14 for c in cases)
    assert all(c['outputs']['requirements'] for c in cases)


def row(case='one', group='baseline', tokens=100, calls=2, status='completed'):
    return {'case_id':case,'group':group,'status':status,'tool_calls':calls,
            'model_calls':1,'elapsed_seconds':1,
            'usage':{'usage_complete':tokens is not None,'input_tokens':tokens,'output_tokens':5}}


def test_failed_task_costs_are_included_and_unknown_usage_is_not_zero():
    result = summarize([row(),row('two',tokens=None,status='failed')], expected_cases=8)
    group = result['groups']['baseline']
    assert group['runs'] == 2
    assert group['mean_tool_calls'] == 2
    assert group['mean_input_tokens'] is None
    assert group['task_acceptance_rate'] is None
    assert result['paired_cases'] == 0
    assert result['input_token_reduction'] is None


def test_reduction_requires_all_expected_pairs_and_complete_usage():
    records = [row(),row(group='optimized',tokens=80)]
    assert summarize(records,expected_cases=8)['input_token_reduction'] is None
    assert summarize(records,expected_cases=1)['input_token_reduction'] == pytest.approx(.2)


def test_unknown_usage_in_either_group_prevents_reduction():
    assert summarize([row(),row(group='optimized',tokens=None)],expected_cases=1)['input_token_reduction'] is None


def test_duplicate_trials_are_not_silently_counted_as_more_questions():
    with pytest.raises(ValueError,match='duplicate'):
        summarize([row(),row()],expected_cases=8)


@pytest.mark.asyncio
async def test_local_trial_passes_only_question_and_corpus_and_keeps_failed_result(tmp_path):
    from types import SimpleNamespace
    from deeptrace.evaluation.local_sample import execute_case
    from deeptrace.harness.model_budget import RunBudgetModelGateway
    from strategies.fixtures import build_gateway_fixture
    fixture = build_gateway_fixture(model_gateway=RunBudgetModelGateway(object()))
    from dataclasses import replace
    context_for_run = replace(fixture.context,tool_gateway=fixture.gateway._inner)
    released = []
    async def invoke(request, *, context, config):
        assert request.question == 'Only the question'
        assert context.memory_store is context.memory_retriever is None
        assert len(context.source_evidence_ids) == 14
        assert 'golden answer' not in str(request)
        raise RuntimeError('task failed')
    bundle = SimpleNamespace(
        context_factory=lambda run_id,**kwargs:context_for_run,
        service=SimpleNamespace(invoke=invoke),release_run=released.append)
    case = build_cases()[0]
    case['inputs']['question'] = 'Only the question'
    case['outputs']['answer'] = 'golden answer'
    result = await execute_case(bundle,case,'baseline',tmp_path,SimpleNamespace(research_max_seconds=1))
    assert result['status'] == 'failed'
    assert result['error_code'] == 'RuntimeError'
    assert len(released) == 1
    assert (tmp_path/'baseline'/case['metadata']['id']/'metrics.json').is_file()


@pytest.mark.asyncio
async def test_unavailable_preflight_does_not_start_tasks_or_exit_as_success(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from deeptrace.config import Settings
    from deeptrace.evaluation import local_sample
    settings = Settings('test','https://example.com/v1','model','test',memory_retrieval='lexical')
    monkeypatch.setattr(Settings,'from_env',lambda:settings)
    async def blocked(*args):
        return False
    monkeypatch.setattr(local_sample,'probe',blocked)
    def forbidden(*args,**kwargs):
        raise AssertionError('Must not start task runtimes after failed probe')
    monkeypatch.setattr('deeptrace.application.assembly.build_harness_runtime',forbidden)
    code = await local_sample.main(SimpleNamespace(output=tmp_path,run=True))
    assert code == 2
    import json
    assert json.loads((tmp_path/'status.json').read_text())['executed_cases'] == 0
