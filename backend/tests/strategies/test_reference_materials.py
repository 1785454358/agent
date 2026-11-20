"""The reference table must match final visibility, not historical reads."""

import json

import pytest

from deeptrace.domain import ResearchRequirement
from deeptrace.domain.evidence_anchor import ReadEvidenceAnchor
from deeptrace.harness.token_budget import TokenBudgetConfig, count_tokens
from deeptrace.strategies.evaluation_materials import assemble_reference_evaluation_view
from deeptrace.tools.evidence_store import EvidenceDraft
from strategies.fixtures import FIXED_NOW, TENANT_ID, build_gateway_fixture


@pytest.mark.asyncio
@pytest.mark.parametrize("tokens", [150, 2000])
async def test_overlapping_candidate_supports_do_not_expose_or_prioritize_claim(tokens):
    from deeptrace.domain import EvidenceSupport, Finding

    fixture = build_gateway_fixture()
    body = "Context key is mandatory; never omit it. " + "filler. " * 600
    record = await seed(fixture, 1, body)
    supports = [
        EvidenceSupport(
            evidence_id=record.id,
            version=record.version,
            content_hash=record.content_hash,
            start=a,
            end=b,
            quote=body[a:b],
        )
        for a, b in [(0, 39), (0, 24)]
    ]
    finding = Finding(
        id="research-1",
        claim="The context key is mandatory. " * 20,
        evidence_ids=[record.id],
        confidence=0.8,
        supports=supports,
    )
    view = await assemble_reference_evaluation_view(
        fixture.context,
        question="context key",
        requirements=[ResearchRequirement(id="r1", description="key")],
        evidence_ids=[record.id],
        findings=[],
        read_anchors=[],
        research_findings=[finding],
        budget=TokenBudgetConfig(
            context_tokens=tokens, output_reserve_tokens=0, safety_tokens=0
        ),
    )
    data = json.loads(view.prompt.split("EVIDENCE_VIEW_JSON:\n", 1)[1])
    assert not data["research_findings"]
    assert finding.claim not in view.prompt
    assert view.allocation.used_tokens == count_tokens(view.prompt)


@pytest.mark.asyncio
async def test_stale_candidate_never_exposes_claim():
    from deeptrace.domain import EvidenceSupport, Finding

    fixture = build_gateway_fixture()
    record = await seed(fixture, 1, "valid body")
    finding = Finding(
        id="research-stale",
        claim="SECRET FALSE CLAIM",
        evidence_ids=[record.id],
        confidence=0.8,
        supports=[
            EvidenceSupport(
                evidence_id=record.id,
                version=99,
                content_hash=record.content_hash,
                start=0,
                end=5,
                quote="valid",
            )
        ],
    )
    view = await assemble_reference_evaluation_view(
        fixture.context,
        question="body",
        requirements=[],
        evidence_ids=[record.id],
        findings=[],
        read_anchors=[],
        research_findings=[finding],
    )
    assert finding.claim not in view.prompt


async def seed(fixture, index, body, tenant=TENANT_ID):
    return await fixture.evidence_store.ingest(
        tenant,
        EvidenceDraft(
            canonical_url=f"https://example.com/material-{index}",
            title=f"Material {index}",
            media_type="text/plain",
            body=body,
            fetched_at=FIXED_NOW,
            source_quality=0.9,
        ),
    )


@pytest.mark.asyncio
async def test_parallel_tracks_after_eighth_source_remain_visible_within_token_budget():
    fixture = build_gateway_fixture()
    records = [await seed(fixture, i, f"Independent track {i}: cancellation detail {i}.")
               for i in range(16)]
    view = await assemble_reference_evaluation_view(
        fixture.context, question="Compare all independent tracks and cancellation",
        requirements=[ResearchRequirement(id="r1", description="Compare cancellation")],
        evidence_ids=[r.id for r in records], findings=[], read_anchors=[],
        budget=TokenBudgetConfig(context_tokens=8000, output_reserve_tokens=0, safety_tokens=0),
    )
    assert {p.evidence_id for p in view.passages} == {r.id for r in records}
    assert view.allocation.used_tokens == count_tokens(view.prompt) <= 8000


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["workflow", "plan_execute", "multi_agent"])
async def test_late_track_sources_survive_full_evaluation_protocol(mode):
    from langchain_core.messages import AIMessage
    from langgraph.runtime import Runtime
    from deeptrace.strategies.workflow.nodes import evaluate_node as workflow
    from deeptrace.strategies.plan_execute.nodes import evaluate_node as plan_execute
    from deeptrace.strategies.multi_agent.nodes import supervisor_evaluate_node as multi_agent
    from strategies.fixtures import evaluation_payload_from_view
    from strategies.workflow.test_graph import _research_input

    class Assessor:
        calls = 0

        async def invoke(self, *, messages, **kwargs):
            self.calls += 1
            prompt = str(messages[-1].content)
            return AIMessage(content=json.dumps(evaluation_payload_from_view(
                prompt, **({"sufficient": True} if mode == "workflow" else {}),
            )))

    assessor = Assessor()
    fixture = build_gateway_fixture(model_gateway=assessor)
    records = [await seed(fixture, i, f"Cancellation detail for track {i}.") for i in range(16)]
    result = await {"workflow": workflow, "plan_execute": plan_execute, "multi_agent": multi_agent}[mode]({
        **_research_input("Compare cancellation"), "requirements": [ResearchRequirement(id="r1", description="Cancellation")],
        "evidence_ids": [r.id for r in records], "evidence_contract_version": 3,
    }, Runtime(context=fixture.context))
    assert assessor.calls == 1
    assert all(result["source_eligibility"][r.id] == "eligible" for r in records)
    assert result["coverage"].items[0].status == "covered"


@pytest.mark.asyncio
@pytest.mark.parametrize("tokens", [0, 250, 600, 2000])
async def test_final_reference_map_and_telemetry_follow_actual_token_selection(tokens):
    fixture = build_gateway_fixture()
    body = "Alpha statement. " * 180
    record = await seed(fixture, 1, body)
    view = await assemble_reference_evaluation_view(
        fixture.context,
        question="Explain Alpha",
        requirements=[ResearchRequirement(id="r1", description="Explain Alpha")],
        evidence_ids=[record.id],
        findings=[],
        read_anchors=[],
        budget=TokenBudgetConfig(
            context_tokens=tokens, output_reserve_tokens=0, safety_tokens=0
        ),
    )
    payload = json.loads(view.prompt.split("EVIDENCE_VIEW_JSON:\n", 1)[1])
    assert [p["ref"] for p in payload["passages"]] == list(view.references)
    assert [p["text"] for p in payload["passages"]] == [
        p.text for p in view.references.values()
    ]
    assert all(
        body[p.start : p.end] == p.text and len(p.text) <= 500 for p in view.passages
    )
    assert view.allocation.used_tokens == count_tokens(view.prompt)
    if not view.allocation.pinned_overflow:
        assert view.allocation.used_tokens <= tokens
    else:
        assert not view.references
    visible = {p.passage_id for p in view.passages}
    assert {
        p["passage_id"]
        for kind, p in fixture.events.events
        if kind == "evidence.view" and p["visibility"]
    } == visible


@pytest.mark.asyncio
async def test_foreign_source_and_sources_beyond_metadata_cap_are_never_visible():
    fixture = build_gateway_fixture()
    records = [await seed(fixture, i, f"fact {i}") for i in range(33)]
    foreign = await seed(fixture, 20, "foreign secret", tenant="other-workspace")
    ids = [foreign.id, *[r.id for r in records]]
    view = await assemble_reference_evaluation_view(
        fixture.context,
        question="fact",
        requirements=[ResearchRequirement(id="r1", description="fact")],
        evidence_ids=ids,
        findings=[],
        read_anchors=[],
    )
    assert "foreign secret" not in view.prompt
    assert foreign.id in view.unread_ids
    assert records[-1].id in view.unread_ids
    assert all(p.evidence_id in {r.id for r in records[:31]} for p in view.passages)


@pytest.mark.asyncio
async def test_quote_unit_capacity_does_not_expose_hidden_refs():
    fixture = build_gateway_fixture()
    records = [await seed(fixture, i, "unrelated filler.\n\n" * 1000) for i in range(3)]
    anchors = [
        ReadEvidenceAnchor(
            evidence_id=r.id,
            version=1,
            content_hash=r.content_hash,
            start=5000 + i * 20,
            end=5001 + i * 20,
        )
        for r in records
        for i in range(64)
    ]
    view = await assemble_reference_evaluation_view(
        fixture.context,
        question="unrelated",
        requirements=[ResearchRequirement(id="r1", description="unrelated")],
        evidence_ids=[r.id for r in records],
        findings=[],
        read_anchors=anchors,
    )
    assert len(view.references) == 128
    assert "p129" not in view.references
    assert "quote_unit_capacity" in view.diagnostics
    assert view.unread_ids
