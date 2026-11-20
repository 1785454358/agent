"""Reporting criteria must not become independent evidence gaps."""
import copy

from deeptrace.strategies.evidence_evaluation import seal_initial_plan
from strategies.test_research_brief import QUERIES, QUESTION, payload


def mixed_plan():
    data = payload()
    data['requirements'].append({'id': 'r3', 'description': '注明日期并区分理论与实验', 'kind': 'output_criterion'})
    data['query_targets'][QUERIES[0]].append('r3')
    return data


def test_reporting_criterion_does_not_create_an_evidence_gap_or_degrade_plan():
    data = mixed_plan()
    original = copy.deepcopy(data)
    queries, contract = seal_initial_plan(QUESTION, data, QUERIES)
    assert queries == QUERIES
    assert not contract['decomposition_degraded']
    assert len(contract['requirements']) == 2
    assert contract['query_targets'] == {QUERIES[0]: ['r1'], QUERIES[1]: ['r2']}
    assert '注明日期并区分理论与实验' in contract['research_brief']['answer_criteria']
    assert data == original


def test_client_design_and_negative_constraint_survive_without_factual_gaps():
    data = payload()
    data['requirements'].extend([
        {'id': 'r5', 'description': '自行设计缺失 Retry-After 时的退避', 'kind': 'design_criterion'},
        {'id': 'r6', 'description': 'POST 无去重承诺时不得假定幂等键保障', 'kind': 'constraint'},
    ])
    data['query_targets'][QUERIES[0]].extend(['r5', 'r6'])
    _, contract = seal_initial_plan(QUESTION, data, QUERIES)
    assert not contract['decomposition_degraded']
    assert len(contract['requirements']) == 2
    assert contract['query_targets'] == {QUERIES[0]: ['r1'], QUERIES[1]: ['r2']}
    assert '自行设计缺失 Retry-After 时的退避' in contract['research_brief']['answer_criteria']
    assert 'POST 无去重承诺时不得假定幂等键保障' in contract['research_brief']['answer_criteria']


def test_explicit_factual_date_question_is_retained():
    data = payload()
    data['requirements'][0].update(description='论文发表于哪一年，实验何时完成？', kind='fact')
    _, contract = seal_initial_plan(QUESTION, data, QUERIES)
    assert not contract['decomposition_degraded']
    assert contract['requirements'][0].description == '论文发表于哪一年，实验何时完成？'


def test_separate_answer_criteria_survive_sealing_without_coverage_items():
    data = payload()
    data['research_brief']['answer_criteria'] = ['注明出处，保留适用条件']
    _, contract = seal_initial_plan(QUESTION, data, QUERIES)
    assert not contract['decomposition_degraded']
    assert len(contract['requirements']) == 2
    assert contract['research_brief']['answer_criteria'] == ['注明出处，保留适用条件']


def test_unknown_requirement_id_is_not_treated_as_a_reporting_criterion():
    data = mixed_plan()
    data['query_targets'][QUERIES[0]].append('unplanned')
    queries, contract = seal_initial_plan(QUESTION, data, QUERIES)
    assert contract['decomposition_degraded']
    assert queries == [QUESTION]


def test_complementary_search_queries_reach_only_their_own_branch():
    from deeptrace.strategies.model_io import branch_context
    data = payload()
    seeds = ['2026 Bose gas long range coherence paper', '2026 many body non equilibrium experiment']
    data['task_briefs'][QUERIES[0]]['search_queries'] = seeds
    _, contract = seal_initial_plan(QUESTION, data, QUERIES)
    assert not contract['decomposition_degraded']
    assert branch_context({**contract, 'question':QUESTION, 'query':QUERIES[0]})['search_queries'] == seeds
    assert branch_context({**contract, 'question':QUESTION, 'query':'new gap query'})['search_queries'] == []


def test_duplicate_search_queries_degrade_before_dispatch():
    data = payload()
    data['task_briefs'][QUERIES[0]]['search_queries'] = ['same query',' same query ']
    _, contract = seal_initial_plan(QUESTION, data, QUERIES)
    assert contract['decomposition_degraded']


def test_planning_does_not_unconditionally_investigate_experiment_completion_date():
    from deeptrace.strategies.planning import planning_instruction

    instruction = planning_instruction("queries", 3)
    assert "实验完成时间单独核查" not in instruction
    assert "仅在用户明确询问实验完成日期" in instruction
