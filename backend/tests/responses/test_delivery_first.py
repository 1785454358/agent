"""Known research limits do not erase a sourced, useful delivery."""

import json
from dataclasses import replace

import pytest
from deeptrace.domain import ResearchMode, ResearchOutcome, ResponseInput, ResponseMode
from deeptrace.domain.evidence_anchor import ReadEvidenceAnchor
from deeptrace.responses.evidence import assemble_response_materials
from deeptrace.responses.graph import build_answer_graph
from langchain_core.messages import AIMessage
from strategies.fixtures import build_gateway_fixture
from strategies.test_reference_materials import seed


async def case():
    fixture = build_gateway_fixture()
    body = (
        "general topic noise. " * 500
        + "\n\nLATE_RULE: keep the condition and its exception."
    )
    record = await seed(fixture, 1, body)
    start = body.index("LATE_RULE")
    research = ResearchOutcome(
        delivery_first=True,
        mode=ResearchMode.PLAN_EXECUTE,
        evidence_contract_version=3,
        evidence_ids=[record.id],
        executed_steps=2,
        read_anchors=[
            ReadEvidenceAnchor(
                evidence_id=record.id,
                version=record.version,
                content_hash=record.content_hash,
                start=start,
                end=len(body),
            )
        ],
        termination_reason="completed",
        unresolved_gaps=["Another detail remains unknown."],
    )
    request = ResponseInput(
        question="Explain the general topic",
        response_mode=ResponseMode.ANSWER,
        research_outcome=research,
        active_evidence_ids=[record.id],
    )
    return fixture, record, request


@pytest.mark.asyncio
async def test_already_read_tail_is_used_without_another_keyword_crop_or_coverage_gate():
    fixture, record, request = await case()
    view = await assemble_response_materials(fixture.context, request, [record], 200)
    assert "LATE_RULE" in view.sources[0]
    assert "general topic noise" not in view.sources[0]
    assert view.issue is None


@pytest.mark.asyncio
async def test_limited_sourced_answer_is_delivered_with_one_writer_for_ordinary_question():
    fixture, _, request = await case()
    calls = []

    class Model:
        async def invoke(self, *, messages, **kwargs):
            calls.append(messages)
            assert "LATE_RULE" in str(messages)
            return AIMessage(
                content=json.dumps(
                    {"content": "已取得的规则有条件和例外 [1]；另一项本次未核实。"}
                )
            )

    result = await build_answer_graph().ainvoke(
        {"response_input": request},
        context=replace(
            fixture.context, model_gateway=Model(), response_fact_review=True
        ),
    )
    assert result["outcome"].partial_reason is None
    assert result["outcome"].citations
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_optional_review_protocol_failure_keeps_the_sourced_report():
    fixture, _, request = await case()
    calls = []
    request = request.model_copy(update={"question": "设计一个带约束的方案"})

    class Model:
        async def invoke(self, *, messages, **kwargs):
            calls.append(messages)
            if len(calls) > 1:
                return AIMessage(content='{"checks":"broken auxiliary protocol"}')
            return AIMessage(
                content=json.dumps(
                    {"content": "方案遵循原文条件和例外 [1]；另一项未核实。"}
                )
            )

    result = await build_answer_graph().ainvoke(
        {"response_input": request},
        context=replace(
            fixture.context, model_gateway=Model(), response_fact_review=True
        ),
    )
    assert "方案遵循" in result["outcome"].content
    assert "以下保留" not in result["outcome"].content
    assert len(calls) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field,value", [("version", 99), ("content_hash", "sha256:" + "0" * 64)]
)
async def test_stale_anchor_is_not_visible_or_citable(field, value):
    fixture, record, request = await case()
    request.research_outcome.read_anchors = [
        request.research_outcome.read_anchors[0].model_copy(update={field: value})
    ]
    view = await assemble_response_materials(fixture.context, request, [record], 200)
    assert not view.passages_by_source[record.id]
    result = await build_answer_graph().ainvoke(
        {"response_input": request}, context=fixture.context
    )
    assert result["outcome"].partial_reason == "no_evidence"
    assert not result["outcome"].citations


def test_new_delivery_status_is_separate_from_unknown_coverage_and_legacy_semantics():
    from deeptrace.harness.graph import _finalize_turn
    from deeptrace.harness.state import new_turn
    from deeptrace.responses.citations import validate_citations
    from deeptrace.responses.models import ResponseDraft

    research = ResearchOutcome(
        mode=ResearchMode.PLAN_EXECUTE,
        delivery_first=True,
        evidence_contract_version=3,
        executed_steps=1,
        termination_reason="completed",
    )
    turn = new_turn("new-delivery", "Question", ResearchMode.PLAN_EXECUTE)
    turn.update(
        research_outcome=research,
        response_outcome=validate_citations(
            ResponseDraft(
                response_mode=ResponseMode.ANSWER,
                content="A useful limited answer [1].",
            ),
            loaded_evidence_ids=["evidence-1"],
        ),
    )
    assert _finalize_turn({"turn": turn})["turn"]["status"].value == "completed"
    assert research.coverage is None
    turn["research_outcome"] = research.model_copy(update={"delivery_first": False})
    assert _finalize_turn({"turn": turn})["turn"]["status"].value == "partial"
    turn["research_outcome"] = research
    turn["response_outcome"] = turn["response_outcome"].model_copy(
        update={"partial_reason": "no_evidence"}
    )
    assert _finalize_turn({"turn": turn})["turn"]["status"].value == "partial"


@pytest.mark.asyncio
async def test_body_changed_under_the_same_metadata_is_not_used(monkeypatch):
    fixture, record, request = await case()
    original = await fixture.evidence_store.read_body(
        fixture.context.workspace_id, record.id
    )

    async def corrupted(*args, **kwargs):
        return "x" * len(original)

    monkeypatch.setattr(fixture.evidence_store, "read_body", corrupted)
    view = await assemble_response_materials(fixture.context, request, [record], 200)
    assert view.passages_by_source[record.id] == ()
