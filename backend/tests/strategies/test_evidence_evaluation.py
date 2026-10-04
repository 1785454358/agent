"""Only exact quotes in the model-visible source view may support findings."""

import json
from dataclasses import replace

import pytest
from langgraph.runtime import Runtime

from deeptrace.domain import (
    CoverageAssessment,
    EvidenceSupport,
    Finding,
    ResearchMode,
    ResearchRequirement,
)
from deeptrace.harness.token_budget import TokenBudgetConfig
from deeptrace.strategies import evidence_evaluation as evaluation
from deeptrace.tools import evidence_views
from deeptrace.tools.evidence_store import EvidenceDraft
from deeptrace.tools.evidence_views import EvidencePassage
from strategies.fixtures import (
    FIXED_NOW,
    TENANT_ID,
    ScriptedModelGateway,
    build_gateway_fixture,
)


def _draft(**kwargs):
    assert hasattr(evaluation, "SupportDraft"), "source support draft not implemented"
    return evaluation.SupportDraft(**kwargs)


def _passage(text="abc abc"):
    return EvidencePassage("e-1", 2, "hash", "p-1", 10, 10 + len(text), 1, 1, text)


@pytest.mark.parametrize(
    "quote,passage_id", [("abc", "p-1"), ("abc abc", "p-2"), ("invented", "p-1")]
)
def test_repeated_hidden_or_invented_quotes_are_rejected(quote, passage_id):
    draft = _draft(evidence_id="e-1", passage_id=passage_id, quote=quote)
    assert evaluation.resolve_support(draft, (_passage(),)) is None


def test_exact_quote_preserves_unicode_offsets_version_and_hash():
    passage = _passage("prefix 中文🙂 suffix")
    draft = _draft(evidence_id="e-1", passage_id="p-1", quote="中文🙂")
    support = evaluation.resolve_support(draft, (passage,))
    assert support == EvidenceSupport(
        evidence_id="e-1",
        version=2,
        content_hash="hash",
        start=17,
        end=20,
        quote="中文🙂",
    )


def test_model_draft_cannot_supply_host_resolved_coordinates():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        _draft(evidence_id="e-1", passage_id="p-1", quote="abc", start=10)


def _requirements():
    return [ResearchRequirement(id="r1", description="Explain Store")]


def _coverage(status="covered", requirement_id="r1", finding_ids=None):
    return CoverageAssessment(
        items=[
            {
                "requirement_id": requirement_id,
                "status": status,
                "reason": "claim from source",
                "finding_ids": finding_ids or ["f1"],
            }
        ]
    )


def test_covered_without_a_supported_finding_is_downgraded_to_missing():
    assert hasattr(evaluation, "normalize_coverage")
    finding = Finding(
        id="f1", claim="unsupported", evidence_ids=["e-1"], confidence=0.9
    )
    result = evaluation.normalize_coverage(_requirements(), _coverage(), [finding])
    assert result.items[0].status == "missing"
    assert result.items[0].finding_ids == []


def test_coverage_cannot_remove_or_replace_fixed_requirements():
    assert hasattr(evaluation, "normalize_coverage")
    with pytest.raises(ValueError, match="invalid_requirement_coverage"):
        evaluation.normalize_coverage(
            _requirements(), _coverage(requirement_id="r2"), []
        )


def test_conflicting_does_not_become_covered_just_because_quotes_exist():
    assert hasattr(evaluation, "normalize_coverage")
    support = EvidenceSupport(
        evidence_id="e-1",
        version=2,
        content_hash="hash",
        start=10,
        end=17,
        quote="abc abc",
    )
    finding = Finding(
        id="f1", claim="claim", evidence_ids=["e-1"], confidence=0.9, supports=[support]
    )
    result = evaluation.normalize_coverage(
        _requirements(), _coverage(status="conflicting"), [finding]
    )
    assert result.items[0].status == "conflicting"


async def _source(fixture, body, url="https://example.com/store"):
    return await fixture.evidence_store.ingest(
        TENANT_ID,
        EvidenceDraft(
            canonical_url=url,
            title="title is not source support",
            media_type="text/plain",
            body=body,
            fetched_at=FIXED_NOW,
            source_quality=0.9,
        ),
    )


@pytest.mark.asyncio
async def test_evaluation_reads_tail_and_serializes_only_actual_source_passages():
    assert hasattr(evaluation, "assemble_evaluation_view")
    fixture = build_gateway_fixture()
    fact = "Store keeps cross-thread facts."
    record = await _source(fixture, "Unrelated.\n\n" * 700 + fact)
    view = await evaluation.assemble_evaluation_view(
        fixture.context,
        question="Store",
        requirements=_requirements(),
        evidence_ids=[record.id],
        findings=[],
    )
    material = json.JSONDecoder().raw_decode(
        view.prompt.split("EVIDENCE_VIEW_JSON:", 1)[1].lstrip()
    )[0]
    assert fact in str(material["passages"])
    assert material["requirements"] == [r.model_dump() for r in _requirements()]
    assert "title is not source support" not in [p.text for p in view.passages]
    for passage in view.passages:
        assert (
            passage.text
            == (await fixture.evidence_store.read_body(TENANT_ID, record.id))[
                passage.start : passage.end
            ]
        )
    assert view.unread_ids == ()
    assert fixture.events.events
    assert all(
        "text" not in payload and "body" not in payload
        for _, payload in fixture.events.events
    )


@pytest.mark.asyncio
async def test_token_dropped_passage_cannot_be_used_to_resolve_support():
    assert hasattr(evaluation, "assemble_evaluation_view")
    fixture = build_gateway_fixture()
    record = await _source(fixture, "Store keeps cross-thread facts. " * 60)
    view = await evaluation.assemble_evaluation_view(
        fixture.context,
        question="Store",
        requirements=_requirements(),
        evidence_ids=[record.id],
        findings=[],
        budget=TokenBudgetConfig(
            context_tokens=160, output_reserve_tokens=0, safety_tokens=0
        ),
    )
    assert view.passages == ()
    assert view.unread_ids == (record.id,)
    assert not view.allocation.truncated
    assert json.loads(view.prompt.split("EVIDENCE_VIEW_JSON:", 1)[1])["passages"] == []


@pytest.mark.asyncio
async def test_one_missing_source_does_not_erase_other_valid_sources():
    assert hasattr(evaluation, "assemble_evaluation_view")
    fixture = build_gateway_fixture()
    record = await _source(fixture, "Store keeps cross-thread facts.")
    view = await evaluation.assemble_evaluation_view(
        fixture.context,
        question="Store",
        requirements=_requirements(),
        evidence_ids=["missing", record.id],
        findings=[],
    )
    assert [p.evidence_id for p in view.passages] == [record.id]
    assert view.unread_ids == ("missing",)


@pytest.mark.asyncio
async def test_one_source_storage_failure_does_not_erase_other_visible_sources():
    fixture = build_gateway_fixture()
    record = await _source(fixture, "Store keeps cross-thread facts.")

    class MixedStore:
        async def get(self, tenant, identity):
            if identity == "offline-source":
                raise RuntimeError("individual source unavailable")
            return await fixture.evidence_store.get(tenant, identity)

        async def read_body(self, tenant, identity):
            return await fixture.evidence_store.read_body(tenant, identity)

    view = await evaluation.assemble_evaluation_view(
        replace(fixture.context, evidence_store=MixedStore()),
        question="Store",
        requirements=_requirements(),
        evidence_ids=["offline-source", record.id],
        findings=[],
    )
    assert [p.evidence_id for p in view.passages] == [record.id]
    assert view.unread_ids == ("offline-source",)


@pytest.mark.asyncio
async def test_source_and_per_source_limits_are_bounded_and_unread_is_explicit():
    assert hasattr(evaluation, "assemble_evaluation_view")
    fixture = build_gateway_fixture()
    ids = [
        (await _source(fixture, "Store " * 1000, url=f"https://example.com/{index}")).id
        for index in range(9)
    ]
    view = await evaluation.assemble_evaluation_view(
        fixture.context,
        question="Store",
        requirements=_requirements(),
        evidence_ids=ids,
        findings=[],
    )
    assert len({p.evidence_id for p in view.passages}) <= 8
    assert ids[-1] in view.unread_ids
    for evidence_id in ids:
        assert (
            sum(len(p.text) for p in view.passages if p.evidence_id == evidence_id)
            <= 3000
        )


@pytest.mark.asyncio
async def test_accepted_support_is_selected_before_query_prefix_and_stale_support_is_ignored():
    assert hasattr(evidence_views, "select_supported_passages")
    fixture = build_gateway_fixture()
    body = "irrelevant " * 1000 + "A precise accepted fact."
    record = await _source(fixture, body)
    start = body.index("A precise")
    support = EvidenceSupport(
        evidence_id=record.id,
        version=record.version,
        content_hash=record.content_hash,
        start=start,
        end=len(body),
        quote=body[start:],
    )
    selected = evidence_views.select_supported_passages(
        record, body, [support], question="irrelevant", limit=200
    )
    assert any(support.quote in p.text for p in selected)
    assert sum(len(p.text) for p in selected) <= 200
    forged = support.model_copy(update={"content_hash": "wrong"})
    selected = evidence_views.select_supported_passages(
        record, body, [forged], question="irrelevant", limit=200
    )
    assert all(support.quote not in p.text for p in selected)


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", list(ResearchMode))
@pytest.mark.parametrize("case", ["valid", "metadata_only", "omitted_requirement"])
async def test_actual_mode_evaluation_requires_visible_support_and_complete_requirement_set(
    mode, case
):
    from deeptrace.strategies.multi_agent.nodes import (
        supervisor_evaluate_node as ma_evaluate,
    )
    from deeptrace.strategies.plan_execute.nodes import evaluate_node as pe_evaluate
    from deeptrace.strategies.workflow.nodes import evaluate_node as wf_evaluate

    fact = "Store keeps cross-thread facts."

    def model_response(prompt):
        assert "EVIDENCE_VIEW_JSON:" in prompt, "evaluator still receives only metadata"
        material = json.JSONDecoder().raw_decode(
            prompt.split("EVIDENCE_VIEW_JSON:", 1)[1].lstrip()
        )[0]
        assert fact in str(material["passages"])
        passage = material["passages"][0]
        support = {"ref": passage["ref"]}
        findings = [
            {
                "id": "f1",
                "claim": fact,
                "confidence": 0.9,
                "supports": [] if case == "metadata_only" else [support],
            }
        ]
        payload = {
            "findings": findings,
            "source_checks": [{"source": s["source"], "status": "eligible",
                               "reason": "fixture source"} for s in material["sources"]],
            "unresolved_gaps": [],
            "coverage": {
                "items": [
                    {
                        "requirement_id": "r1",
                        "status": "covered",
                        "reason": "the source explains the scope",
                        "finding_ids": ["f1"],
                    }
                ]
            },
        }
        if mode is ResearchMode.WORKFLOW:
            payload["sufficient"] = True
        else:
            payload.update(action="complete", reason="covered")
        return json.dumps(payload)

    model = ScriptedModelGateway({"evaluator": model_response})
    fixture = build_gateway_fixture(model_gateway=model)
    record = await _source(fixture, "Unrelated.\n\n" * 700 + fact)
    state = {
        "run_id": "run-1",
        "thread_id": "thread-1",
        "question": "Explain Store",
        "current_date": "2026-10-02",
        "timezone": "Asia/Shanghai",
        "evidence_contract_version": 3,
        "requirements": _requirements(),
        "evidence_ids": [record.id],
    }
    if case == "omitted_requirement":
        state["requirements"] = [
            *_requirements(),
            ResearchRequirement(id="r2", description="Explain Checkpoints"),
        ]
    node = {
        ResearchMode.WORKFLOW: wf_evaluate,
        ResearchMode.PLAN_EXECUTE: pe_evaluate,
        ResearchMode.MULTI_AGENT: ma_evaluate,
    }[mode]
    result = await node(state, Runtime(context=fixture.context))
    assert len(model.calls) == 1
    assert result.get("coverage") is not None
    if case == "valid":
        assert result["coverage"].items[0].status == "covered"
        support = result["findings"][0].supports[0]
        body = await fixture.evidence_store.read_body(TENANT_ID, record.id)
        assert support.quote == body[support.start : support.end] == fact
        assert support.content_hash == record.content_hash
    else:
        assert all(item.status == "missing" for item in result["coverage"].items)
        assert result["unresolved_gaps"]
        decision = result[
            "evaluation" if mode is not ResearchMode.PLAN_EXECUTE else "decision"
        ]
        if mode is ResearchMode.WORKFLOW:
            assert not decision.sufficient
        else:
            assert decision.action != "complete"
