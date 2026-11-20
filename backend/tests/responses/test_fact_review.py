"""Final drafting review checks only the writer-visible original passages."""
import json
from dataclasses import replace

import pytest
from langchain_core.messages import AIMessage

from deeptrace.responses.graph import build_answer_graph
from responses.test_supported_findings import _case


class ReviewingModel:
    def __init__(self, reviewed):
        self.reviewed = reviewed
        self.prompts = []

    async def invoke(self, *, role, messages, tools=None):
        prompt = '\n'.join(str(m.content) for m in messages)
        self.prompts.append(prompt)
        if 'ANSWER_REVIEW_JSON:' in prompt:
            assert 'Rare supported qualifier.' in prompt
            return AIMessage(content=self.reviewed)
        return AIMessage(content=json.dumps({'content':'这一结果适用于所有场景 [1]。'}))


@pytest.mark.asyncio
@pytest.mark.parametrize('failure_stage', ['draft','review'])
async def test_one_transient_response_failure_recovers_through_shared_budget(failure_stage):
    from deeptrace.domain import ErrorCategory
    from deeptrace.harness.model_gateway import ModelCallError
    from deeptrace.harness.model_budget import RunBudgetModelGateway
    payload, _, fixture, _ = await _case()
    class FlakyModel(ReviewingModel):
        failed = False
        async def invoke(self, *, role, messages, tools=None):
            is_review = 'ANSWER_REVIEW_JSON:' in str(messages[-1].content)
            if not self.failed and is_review == (failure_stage=='review'):
                self.failed = True
                raise ModelCallError(ErrorCategory.TRANSIENT)
            return await super().invoke(role=role, messages=messages, tools=tools)
    model = FlakyModel(json.dumps({'content':'受 Rare supported qualifier. 限制 [1]。','issues':[], 'unanswered_points':[]}))
    budget = RunBudgetModelGateway(model)
    context = replace(fixture.context, model_gateway=budget, response_fact_review=True)
    result = await build_answer_graph().ainvoke({'response_input':payload},context=context)
    assert result['outcome'].partial_reason is None
    assert budget.used_calls == 3


@pytest.mark.asyncio
async def test_reviewed_qualified_answer_replaces_overgeneralized_draft():
    payload, _, fixture, _ = await _case()
    model = ReviewingModel(json.dumps({'content':'原文结果受 Rare supported qualifier. 限制 [1]。','issues':['原稿泛化适用范围'], 'unanswered_points': []}))
    context = replace(fixture.context, model_gateway=model, response_fact_review=True)
    result = await build_answer_graph().ainvoke({'response_input':payload}, context=context)
    assert '所有场景' not in result['outcome'].content
    assert 'Rare supported qualifier.' in result['outcome'].content
    assert len(model.prompts) == 2
    assert result['outcome'].partial_reason is None


@pytest.mark.asyncio
@pytest.mark.parametrize("review", [
    'not json',
    json.dumps({'content': '这一结果适用于所有场景 [1]。', 'issues': ['重复原因'] * 9}),
    json.dumps({'content': '受 Rare supported qualifier. 限制 [1]。', 'issues': []}),
])
async def test_malformed_review_does_not_publish_unreviewed_overstatement(review):
    payload, _, fixture, _ = await _case()
    model = ReviewingModel(review)
    context = replace(fixture.context, model_gateway=model, response_fact_review=True)
    result = await build_answer_graph().ainvoke({'response_input':payload}, context=context)
    assert '所有场景' not in result['outcome'].content
    assert result['outcome'].partial_reason == 'answer_review_unavailable'
    assert len(model.prompts) == 3


@pytest.mark.asyncio
async def test_failed_review_preserves_original_supported_content_instead_of_only_source_titles():
    payload, _, fixture, _ = await _case()
    model = ReviewingModel('not json')
    context = replace(fixture.context, model_gateway=model, response_fact_review=True)
    result = await build_answer_graph().ainvoke({'response_input': payload}, context=context)
    outcome = result['outcome']
    assert 'Rare supported qualifier.' in outcome.content
    assert '所有场景' not in outcome.content
    assert outcome.citations
    assert outcome.partial_reason == 'answer_review_unavailable'


@pytest.mark.asyncio
async def test_budget_limited_report_keeps_independent_focused_fact_review():
    from deeptrace.domain import ResponseMode
    from deeptrace.responses.graph import build_report_graph
    from deeptrace.harness.model_budget import RunBudgetModelGateway
    payload, _, fixture, _ = await _case()
    payload.response_mode = ResponseMode.REPORT
    model = ReviewingModel(json.dumps({'content': '## 研究报告\n\n结论受 Rare supported qualifier. 限制 [1]。',
        'issues': [], 'unanswered_points': []}))
    gateway = RunBudgetModelGateway(model)
    result = await build_report_graph().ainvoke({'response_input': payload}, context=replace(
        fixture.context, model_gateway=gateway, response_fact_review=True))
    assert 'Rare supported qualifier.' in result['outcome'].content
    assert result['outcome'].partial_reason is None
    assert gateway.used_calls == 2
    assert 'ANSWER_REVIEW_JSON:' not in model.prompts[0]
    assert json.loads(model.prompts[1].split('ANSWER_REVIEW_JSON:\n')[1])['draft']
    assert any(kind == 'response.fact_review.completed' and data['drafting_mode'] == 'draft_then_focused_review'
               for kind, data in fixture.events.events)


@pytest.mark.asyncio
async def test_budgeted_report_corrects_small_length_overrun_in_planned_fact_review():
    from deeptrace.domain import ResponseMode
    from deeptrace.responses.graph import build_report_graph
    from deeptrace.harness.model_budget import RunBudgetModelGateway
    payload, _, fixture, _ = await _case()
    payload.response_mode = ResponseMode.REPORT
    important = 'Rare supported qualifier.'
    draft = '## Report\n\n' + 'Relevant details. ' * 10 + '\n\n' + important + ' [1].'
    class ReviewingOverrun:
        async def invoke(self, *, role, messages, tools=None):
            prompt = str(messages[-1].content)
            if 'ANSWER_REVIEW_JSON:\n' in prompt:
                received = json.loads(prompt.split('ANSWER_REVIEW_JSON:\n')[1])['draft']
                content = '结论受 Rare supported qualifier. 限制 [1]。' if important in received else '关键条件丢失 [1]。'
                return AIMessage(content=json.dumps({'content': content, 'issues': [], 'unanswered_points': []}))
            return AIMessage(content=json.dumps({'content': draft}))
    gateway = RunBudgetModelGateway(ReviewingOverrun())
    result = await build_report_graph().ainvoke({'response_input': payload}, context=replace(
        fixture.context, model_gateway=gateway, response_fact_review=True, response_max_content_chars=200))
    assert important in result['outcome'].content
    assert gateway.used_calls == 2


@pytest.mark.asyncio
async def test_quota_exhaustion_during_grounded_synthesis_returns_controlled_partial_without_retry():
    from deeptrace.domain import ResponseMode, ErrorCategory
    from deeptrace.responses.graph import build_report_graph
    from deeptrace.harness.model_budget import RunBudgetModelGateway
    from deeptrace.harness.model_gateway import ModelCallError
    payload, _, fixture, _ = await _case()
    payload.response_mode = ResponseMode.REPORT
    class QuotaModel:
        async def invoke(self, **kwargs):
            raise ModelCallError(ErrorCategory.FATAL, code='model_quota_exhausted')
    gateway = RunBudgetModelGateway(QuotaModel())
    result = await build_report_graph().ainvoke({'response_input': payload}, context=replace(
        fixture.context, model_gateway=gateway, response_fact_review=True))
    assert gateway.used_calls == 1
    assert result['outcome'].partial_reason == 'model_quota_exhausted'
    assert '额度' in result['outcome'].content


@pytest.mark.asyncio
async def test_grounded_synthesis_transport_failure_keeps_verified_material_after_bounded_retry():
    from deeptrace.domain import ResponseMode, ErrorCategory
    from deeptrace.responses.graph import build_report_graph
    from deeptrace.harness.model_budget import RunBudgetModelGateway
    from deeptrace.harness.model_gateway import ModelCallError
    payload, _, fixture, _ = await _case()
    payload.response_mode = ResponseMode.REPORT
    class DisconnectedModel:
        async def invoke(self, **kwargs):
            raise ModelCallError(ErrorCategory.TRANSIENT)
    gateway = RunBudgetModelGateway(DisconnectedModel())
    result = await build_report_graph().ainvoke({'response_input': payload}, context=replace(
        fixture.context, model_gateway=gateway, response_fact_review=True))
    assert gateway.used_calls == 2
    assert result['outcome'].partial_reason == 'model_error'
    assert 'Rare supported qualifier.' in result['outcome'].content


@pytest.mark.asyncio
async def test_partial_review_json_has_one_budgeted_protocol_repair():
    from deeptrace.harness.model_budget import RunBudgetModelGateway
    payload, _, fixture, _ = await _case()
    class IncompleteFirstReview(ReviewingModel):
        review_calls = 0
        async def invoke(self, *, role, messages, tools=None):
            if 'ANSWER_REVIEW_JSON:' in str(messages[-1].content):
                self.review_calls += 1
                if self.review_calls == 1:
                    return AIMessage(content=json.dumps({'issues':['需要修正范围']}))
            return await super().invoke(role=role, messages=messages, tools=tools)
    model = IncompleteFirstReview(json.dumps({
        'issues':['已保留限定条件'], 'unanswered_points':[],
        'content':'受 Rare supported qualifier. 限制 [1]。'}))
    gateway = RunBudgetModelGateway(model)
    result = await build_answer_graph().ainvoke({'response_input':payload},
        context=replace(fixture.context,model_gateway=gateway,response_fact_review=True))
    assert 'Rare supported qualifier.' in result['outcome'].content
    assert result['outcome'].partial_reason is None
    assert model.review_calls == 2
    assert gateway.used_calls == 3


@pytest.mark.asyncio
async def test_review_cannot_introduce_a_nonexistent_citation_number():
    payload, _, fixture, _ = await _case()
    model = ReviewingModel(json.dumps({'content':'新事实 [99]。','issues':[], 'unanswered_points': []}))
    context = replace(fixture.context, model_gateway=model, response_fact_review=True)
    result = await build_answer_graph().ainvoke({'response_input':payload}, context=context)
    assert result['outcome'].partial_reason is not None
    assert '新事实' not in result['outcome'].content


@pytest.mark.asyncio
async def test_review_telemetry_failure_does_not_discard_a_valid_answer():
    payload, _, fixture, _ = await _case()
    model = ReviewingModel(json.dumps({'content':'受 Rare supported qualifier. 限制 [1]。', 'unanswered_points': []}))

    class FailingReviewEventSink:
        async def emit(self, event_type, payload):
            if event_type == 'response.fact_review.completed':
                raise RuntimeError('event transport unavailable')
            await fixture.context.event_sink.emit(event_type, payload)

    context = replace(fixture.context, model_gateway=model, response_fact_review=True,
                      event_sink=FailingReviewEventSink())
    result = await build_answer_graph().ainvoke({'response_input':payload}, context=context)
    assert result['outcome'].partial_reason is None
    assert 'Rare supported qualifier.' in result['outcome'].content


@pytest.mark.asyncio
async def test_review_detected_missing_answer_point_projects_partial():
    payload, _, fixture, _ = await _case()
    model = ReviewingModel(json.dumps({
        'content': '受 Rare supported qualifier. 限制 [1]。尚无证据回答第二个要点。',
        'issues': ['删除了无证据的推断'],
        'unanswered_points': ['第二个用户要点缺乏原文支持'],
    }))
    context = replace(fixture.context, model_gateway=model, response_fact_review=True)
    result = await build_answer_graph().ainvoke({'response_input': payload}, context=context)
    assert result['outcome'].partial_reason == 'answer_review_incomplete'
    assert 'Rare supported qualifier.' in result['outcome'].content
