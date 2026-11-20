import json

import pytest
from langchain_core.messages import AIMessage
from langgraph.runtime import Runtime

from deeptrace.domain import ResearchRequirement, ResearchMode
from deeptrace.strategies.workflow.nodes import evaluate_node as workflow_evaluate
from deeptrace.strategies.plan_execute.nodes import evaluate_node as plan_evaluate
from deeptrace.strategies.multi_agent.nodes import supervisor_evaluate_node
from deeptrace.harness.checkpoint import create_harness_checkpoint_serializer
from strategies.fixtures import build_gateway_fixture, evaluation_payload_from_view
from strategies.test_reference_materials import seed


class DeltaModel:
    evaluation_identity = {'model': 'delta-fixture', 'temperature': 0}

    def __init__(self, *, conflict=False, acknowledge=True):
        self.views = []
        self.attempts = 0
        self.exhausted = False
        self.conflict = conflict
        self.acknowledge = acknowledge

    async def invoke(self, *, messages, **kwargs):
        self.attempts += 1
        if self.exhausted:
            from deeptrace.harness.model_budget import ModelBudgetExceeded
            raise ModelBudgetExceeded('input_tokens')
        prompt = str(messages[-1].content)
        material = json.JSONDecoder().raw_decode(prompt.split('EVIDENCE_VIEW_JSON:', 1)[1].lstrip())[0]
        self.views.append(material)
        payload = evaluation_payload_from_view(prompt, sufficient=True)
        payload.update(action='complete', reason='fixture')
        # Each live strategy retains its own output contract.
        if '"sufficient"' in str(messages[0].content):
            payload.pop('action'); payload.pop('reason')
        else:
            payload.pop('sufficient')
        if len(self.views) == 1:
            payload['coverage']['items'][1].update(status='missing', finding_ids=[], reason='Beta unread')
        if material.get('prior_verified_requirements') and self.acknowledge:
            payload['unchanged_requirement_ids'] = [] if self.conflict else ['r1']
        return AIMessage(content=json.dumps(payload))


NODES = {ResearchMode.WORKFLOW: workflow_evaluate,
         ResearchMode.PLAN_EXECUTE: plan_evaluate,
         ResearchMode.MULTI_AGENT: supervisor_evaluate_node}


async def baseline(model, mode=ResearchMode.WORKFLOW):
    fixture = build_gateway_fixture(model_gateway=model)
    source = await seed(fixture, 1, 'Alpha has a documented stable rule.')
    state = {'run_id':'run-1','thread_id':'thread-1','question':'Explain Alpha and Beta.',
        'current_date':'2026-11-19','timezone':'Asia/Shanghai','evidence_contract_version':3,
        'requirements':[ResearchRequirement(id='r1',description='Alpha rule'),
                        ResearchRequirement(id='r2',description='Beta rule')],
        'evidence_ids':[source.id]}
    result = await NODES[mode](state, Runtime(context=fixture.context))
    assert result['coverage'].items[0].status == 'covered'
    return fixture, {**state, **result}


@pytest.mark.asyncio
async def test_scheduling_and_budget_changes_without_new_text_do_not_rejudge():
    model = DeltaModel()
    fixture, state = await baseline(model)
    serde = create_harness_checkpoint_serializer()
    state = serde.loads_typed(serde.dumps_typed(state))
    result = await workflow_evaluate({**state,'replan_count':2,'completed_tasks':['new query name'],
        'budget':{'tool_calls':7}, 'progress_before_supplement':[]}, Runtime(context=fixture.context))
    assert len(model.views) == 1
    assert result['coverage'] == state['coverage']
    assert result['supplement_completed'] is True


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', list(ResearchMode))
async def test_new_beta_evidence_only_rejudges_beta_and_preserves_alpha(mode):
    model = DeltaModel()
    fixture, state = await baseline(model, mode)
    alpha_claim = state['findings'][0]
    source = await seed(fixture, 2, 'Beta has its own independent documented rule.')
    result = await NODES[mode]({**state, 'evidence_ids':[*state['evidence_ids'],source.id]},
        Runtime(context=fixture.context))
    assert [r['id'] for r in model.views[-1]['requirements']] == ['r2']
    assert all(row.status == 'covered' for row in result['coverage'].items)
    assert alpha_claim in result['findings']
    assert len({f.id for f in result['findings']}) == len(result['findings'])
    assert result['verification'].coverage_complete


@pytest.mark.asyncio
@pytest.mark.parametrize('conflict,acknowledge', [(True,True),(False,False)])
async def test_uncertain_impact_or_possible_conflict_reopens_full_evaluation(conflict, acknowledge):
    model = DeltaModel(conflict=conflict, acknowledge=acknowledge)
    fixture, state = await baseline(model)
    source = await seed(fixture, 2, 'Beta may contradict the earlier Alpha guarantee.')
    await workflow_evaluate({**state,'evidence_ids':[*state['evidence_ids'],source.id]},
        Runtime(context=fixture.context))
    assert len(model.views) == 3
    assert [r['id'] for r in model.views[1]['requirements']] == ['r2']
    assert [r['id'] for r in model.views[2]['requirements']] == ['r1','r2']


@pytest.mark.asyncio
async def test_failed_delta_does_not_retry_a_larger_full_request_or_keep_old_completion():
    model = DeltaModel()
    fixture, state = await baseline(model)
    source = await seed(fixture, 2, 'Beta is now documented but may affect Alpha.')
    model.exhausted = True
    result = await workflow_evaluate({**state,'evidence_ids':[*state['evidence_ids'],source.id]},
        Runtime(context=fixture.context))
    assert model.attempts == 2
    assert not result['verification'].coverage_complete
    assert all(row.status == 'missing' for row in result['coverage'].items)
    assert result['evaluation_snapshot'] is None


@pytest.mark.asyncio
async def test_rereading_an_already_visible_range_is_not_new_evidence():
    from deeptrace.domain import ResearchTopicOutcome
    from deeptrace.domain.evidence_anchor import ReadEvidenceAnchor
    model = DeltaModel()
    fixture, state = await baseline(model)
    record = await fixture.evidence_store.get(fixture.context.workspace_id, state['evidence_ids'][0])
    anchor = ReadEvidenceAnchor(evidence_id=record.id,version=record.version,
        content_hash=record.content_hash,start=0,end=15,queries=['another query'])
    result = await workflow_evaluate({**state,'topic_outcomes':[
        ResearchTopicOutcome(query='another query',evidence_ids=[record.id],read_anchors=[anchor])]},
        Runtime(context=fixture.context))
    assert len(model.views) == 1
    assert result['coverage'] == state['coverage']


@pytest.mark.asyncio
async def test_narrower_source_scope_does_not_show_old_out_of_scope_evidence():
    from dataclasses import replace
    model = DeltaModel()
    fixture, state = await baseline(model)
    source = await seed(fixture, 2, 'Beta is the only source now permitted.')
    context = replace(fixture.context, source_evidence_ids=frozenset({source.id}))
    await workflow_evaluate({**state,'evidence_ids':[*state['evidence_ids'],source.id]}, Runtime(context=context))
    assert [r['id'] for r in model.views[-1]['requirements']] == ['r1','r2']
    assert all('Alpha has a documented' not in p['text'] for p in model.views[-1]['passages'])


@pytest.mark.asyncio
async def test_a_host_invalidated_claim_cannot_be_resurrected_from_cached_coverage():
    model = DeltaModel()
    fixture, state = await baseline(model)
    invalidated = state['verification'].model_copy(update={
        'graph':state['verification'].graph.model_copy(update={'claims':()})})
    await workflow_evaluate({**state,'verification':invalidated}, Runtime(context=fixture.context))
    assert len(model.views) == 2
