import json
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage
from deeptrace.responses.fact_review import review_answer


class Reviewer:
    def __init__(self, payload):
        self.payload = payload

    async def invoke(self, **kwargs):
        return AIMessage(content=json.dumps(self.payload))


@pytest.mark.asyncio
async def test_clean_draft_is_preserved_without_repeating_it_in_model_output():
    result = await review_answer(SimpleNamespace(model_gateway=Reviewer({
        'issues':[], 'unanswered_points':[], 'edits':[],
    })), question='explain', constraints=[], content='Original verified answer. [1]',
        sources=['[1] Original verified answer.'], input_budget=20000)
    assert result.content == 'Original verified answer. [1]'


@pytest.mark.asyncio
async def test_targeted_review_replaces_only_exact_unique_passage():
    result = await review_answer(SimpleNamespace(model_gateway=Reviewer({
        'issues':['POST status does not establish no processing'],
        'unanswered_points':[], 'edits':[{
            'old':'POST 429 is always retryable. [1]',
            'new':'POST 429 alone does not prove safe retry. [1]',
        }],
    })), question='POST 429 without deduplication?', constraints=[],
        content='GET is idempotent. [1]\nPOST 429 is always retryable. [1]',
        sources=['[1] Original specification'], input_budget=20000)
    assert result.content == 'GET is idempotent. [1]\nPOST 429 alone does not prove safe retry. [1]'


@pytest.mark.asyncio
async def test_review_cannot_approve_a_business_risk_override_of_post_safety():
    draft = 'Reference [1]\n```text\nif method == POST and not serverDedupPromise and not acceptDuplicateRisk:\n  stop()\nretry()\n```'
    with pytest.raises(ValueError, match='unsafe_post_retry_override'):
        await review_answer(SimpleNamespace(model_gateway=Reviewer({
            'issues':[], 'unanswered_points':[], 'edits':[],
        })), question='POST 遇到429，服务端未承诺去重时如何重试？', constraints=[],
            content=draft, sources=['[1] Original specification'], input_budget=20000)


@pytest.mark.asyncio
async def test_review_cannot_approve_unbounded_send_under_total_time_budget():
    with pytest.raises(ValueError, match='unbounded_http_send'):
        await review_answer(SimpleNamespace(model_gateway=Reviewer({
            'issues':[], 'unanswered_points':[], 'edits':[],
        })), question='HTTP 重试，总时限30秒，最多3次尝试', constraints=[],
            content='Rule [1]\n```text\nwhile now() < deadline:\n    resp = send(request)\n```',
            sources=['[1] Original specification'], input_budget=20000)


@pytest.mark.asyncio
async def test_renaming_the_post_retry_switch_cannot_hide_unsafe_business_policy():
    with pytest.raises(ValueError, match='unsafe_post_retry_override'):
        await review_answer(SimpleNamespace(model_gateway=Reviewer({
            'issues':[], 'unanswered_points':[], 'edits':[],
        })), question='POST 遇到429，服务端未承诺去重时如何重试？', constraints=[],
            content='POST 可由业务明确接受重复创建时自动重试。 [1]\n```text\nretryable = method == GET or allowPostRetry\n```',
            sources=['[1] Original specification'], input_budget=20000)


@pytest.mark.asyncio
async def test_solution_review_can_patch_a_step_without_rewriting_the_whole_answer():
    from deeptrace.domain.delivery import DeliveryPlan
    plan = DeliveryPlan(approach='Use a bounded request',outline=['Send with remaining timeout'],
        evidence_needs=[{'requirement_id':'r1','query':'request timeout'}],
        consistency_checks=['Every request respects the remaining deadline'])
    result = await review_answer(SimpleNamespace(model_gateway=Reviewer({
        'issues':['Bind the request deadline'], 'unanswered_points':[],
        'edits':[{'old':'send(request)','new':'send(request, timeout=remaining)'}],
        'consistency_checks':[{'check_id':'c1','status':'passed','reason':'Remaining time passed to send'}],
    })), question='Design bounded requests',constraints=[],
        content='Explanation [1]\n```text\nsend(request)\n```',
        sources=['[1] Request accepts timeout'],input_budget=20000, delivery_plan=plan)
    assert result.content == 'Explanation [1]\n```text\nsend(request, timeout=remaining)\n```'
    assert result.consistency_checks[0].status == 'passed'
