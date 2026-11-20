"""A review verdict must point at the revised answer, not an invented path."""

import pytest

from deeptrace.responses.fact_review import apply_review_edits


def review(excerpt, status="passed"):
    return {"issues": [], "unanswered_points": [], "edits": [], "checks": [{
        "kind": "behavior", "status": status, "answer_excerpt": excerpt,
        "reason": "POST without dedup must stop before another send",
        "scenario": "POST + 429 + no dedup -> stop -> no second send",
    }]}


def test_passed_verdict_cannot_invent_a_guard_missing_from_the_answer():
    with pytest.raises(ValueError, match="answer_witness"):
        apply_review_edits("if status == 429: continue", review("if unsafe_post: stop"))


def test_witness_is_checked_against_the_post_edit_answer():
    payload = review("if unsafe_post: stop")
    payload["edits"] = [{"old": "continue", "new": "if unsafe_post: stop"}]
    result = apply_review_edits("if status == 429: continue", payload)
    assert result.checks[0].scenario.endswith("no second send")
    assert result.content == "if status == 429: if unsafe_post: stop"


def test_unresolved_counterexample_is_not_lost_during_focused_revision():
    result = apply_review_edits("if status == 429: continue", review("continue", "unresolved"))
    assert result.checks[0].status == "unresolved"


def test_factual_check_requires_a_source_witness_instead_of_only_passed():
    payload = review("503 requires waiting")
    payload["checks"][0].update(kind="fact", scenario=None)
    with pytest.raises(ValueError, match="source_witness"):
        apply_review_edits("503 requires waiting", payload)


def test_source_witness_accepts_layout_whitespace_but_rejects_changed_modality():
    from deeptrace.responses.review_witnesses import validate_review_witnesses, ReviewCheck
    check = ReviewCheck(kind='fact',status='passed',answer_excerpt='503 permits a delay',reason='same rule',
        source_marker='[1]',source_quote='The server MAY send Retry-After.')
    validate_review_witnesses('503 permits a delay',[check],['[1] RFC\nThe server\nMAY\nsend Retry-After.'])
    with pytest.raises(ValueError,match='source_witness'):
        validate_review_witnesses('503 permits a delay',[check],['[1] RFC\nThe server SHOULD send Retry-After.'])


@pytest.mark.asyncio
async def test_failed_witness_cannot_be_repaired_by_dropping_the_checks():
    import json
    from dataclasses import replace
    from langchain_core.messages import AIMessage
    from deeptrace.responses.fact_review import review_answer
    from strategies.fixtures import build_gateway_fixture

    first = review('Answer [1]')
    first['checks'][0].update(kind='fact',source_marker='[1]',source_quote='invented rule')
    replies = [first, {'issues':[],'unanswered_points':[],'edits':[]}]
    class Model:
        async def invoke(self, **kwargs):
            return AIMessage(content=json.dumps(replies.pop(0)))
    context = replace(build_gateway_fixture().context,model_gateway=Model())
    result = await review_answer(context,question='Explain rule',constraints=[],content='Answer [1]',
        sources=['[1] Source actual rule.'],input_budget=10000)
    assert result.content == 'Answer [1]'
    assert result.checks == []
    assert 'invalid_source_witness' in result.review_diagnostics
    assert len(replies) == 1  # An invalid audit record does not require a full rewrite.


def test_source_witness_tolerates_extracted_layout_around_punctuation():
    from deeptrace.responses.review_witnesses import validate_review_witnesses, ReviewCheck
    check = ReviewCheck(kind='fact',status='passed',answer_excerpt='Methods [1]',reason='same rule',
        source_marker='[1]',source_quote='PUT, DELETE, and safe methods are idempotent.')
    validate_review_witnesses('Methods [1]',[check],['[1] PUT\n,\nDELETE\n,\nand safe methods are idempotent.'])


@pytest.mark.asyncio
async def test_excess_audit_records_do_not_discard_a_valid_revision():
    import json
    from dataclasses import replace
    from langchain_core.messages import AIMessage
    from deeptrace.responses.fact_review import review_answer
    from strategies.fixtures import build_gateway_fixture
    payload = review('Answer [1]')
    payload['checks'] *= 5
    class Model:
        async def invoke(self, **kwargs):
            return AIMessage(content=json.dumps(payload))
    context = replace(build_gateway_fixture().context,model_gateway=Model())
    result = await review_answer(context,question='Explain rule',constraints=[],content='Answer [1]',
        sources=['[1] Source actual rule.'],input_budget=10000)
    assert result.content == 'Answer [1]'
    assert len(result.checks) == 4
    assert 'review_check_capacity_omitted' in result.review_diagnostics


@pytest.mark.asyncio
async def test_overlong_revision_gets_one_bounded_shrink_instead_of_immediate_loss():
    import json
    from dataclasses import replace
    from langchain_core.messages import AIMessage
    from deeptrace.responses.fact_review import review_answer
    from strategies.fixtures import build_gateway_fixture
    original = 'Short draft [1]'
    replies = [
        {'issues':[],'unanswered_points':[],'edits':[{'old':original,'new':'detail '*30+'[1]'}]},
        {'issues':[],'unanswered_points':[],'edits':[{'old':original,'new':'Qualified answer [1]'}]},
    ]
    class Model:
        async def invoke(self, **kwargs):
            return AIMessage(content=json.dumps(replies.pop(0)))
    context = replace(build_gateway_fixture().context,model_gateway=Model())
    result = await review_answer(context,question='Explain rule',constraints=[],content=original,
        sources=['[1] Source actual rule.'],input_budget=10000,max_content_chars=100)
    assert result.content == 'Qualified answer [1]'
    assert len(replies) == 0
