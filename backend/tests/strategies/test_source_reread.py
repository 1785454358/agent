"""Gap recovery selects host coordinates; previews never confer evidence."""

import pytest

from deeptrace.domain.evidence_anchor import ReadEvidenceAnchor
from deeptrace.strategies.source_reread import (
    build_source_outline,
    resolve_source_reads,
)
from deeptrace.tools.evidence_units import select_read_passages
from strategies.fixtures import build_gateway_fixture
from strategies.test_reference_materials import seed


@pytest.mark.asyncio
async def test_outline_and_resolution_are_bounded_and_target_only_sealed_gaps():
    fixture = build_gateway_fixture()
    body = "Ordinary execution.\n\n" + "Later condition requires durable storage."
    record = await seed(fixture, 1, body)
    entries, blocks, diagnostics = await build_source_outline(
        fixture.context,
        [record],
        {record.id: "eligible"},
    )
    assert entries and not diagnostics
    chosen = entries[-1]["block_id"]
    reads = resolve_source_reads(
        {
            "reads": [
                {"block_id": chosen, "target_requirement_ids": ["r1", "r2"]},
                {"block_id": chosen, "target_requirement_ids": ["r2"]},
                {"block_id": "invented", "target_requirement_ids": ["r2"]},
                {"block_id": entries[0]["block_id"], "target_requirement_ids": ["r9"]},
            ]
        },
        blocks,
        gap_ids={"r2"},
        requirement_ids={"r1", "r2"},
    )
    assert len(reads) == 1
    read = reads[0]
    assert read.target_requirement_ids == ["r2"]
    assert read.anchor.evidence_id == record.id
    assert (
        body[read.anchor.start : read.anchor.end].strip()
        == "Later condition requires durable storage."
    )
    assert "preview" not in read.model_dump_json()
    assert (
        resolve_source_reads(
            {"reads": [{"block_id": chosen, "target_requirement_ids": ["r1"]}]},
            blocks,
            gap_ids={"r2"},
            requirement_ids={"r1", "r2"},
        )
        == []
    )
    assert await build_source_outline(
        fixture.context, [record], {record.id: "ineligible"}
    ) == ([], {}, [])


@pytest.mark.asyncio
async def test_outline_limits_and_oversized_units_are_explicit():
    fixture = build_gateway_fixture()
    records = [
        await seed(
            fixture,
            i,
            "x" * 1100 + "\n\n" + "\n\n".join(f"Section {j}." for j in range(70)),
        )
        for i in range(10)
    ]
    entries, blocks, diagnostics = await build_source_outline(
        fixture.context, records, {}
    )
    assert len(entries) <= 128
    assert len({b.anchor.evidence_id for b in blocks.values()}) <= 32
    assert all(b.anchor.end - b.anchor.start <= 900 for b in blocks.values())
    assert any("oversized" in d for d in diagnostics)
    assert any("omitted" in d for d in diagnostics)


@pytest.mark.asyncio
async def test_long_unbroken_section_is_locatable_instead_of_disappearing():
    fixture = build_gateway_fixture()
    body = "## Retention\n\n" + "x" * 1200 + "TAIL_CONDITION"
    record = await seed(fixture, 1, body)
    entries, blocks, diagnostics = await build_source_outline(
        fixture.context, [record], {}, focus_queries=["TAIL_CONDITION"], max_entries=24,
    )
    assert any("TAIL_CONDITION" in body[a.anchor.start:a.anchor.end] for a in blocks.values())
    assert any(e.get("section_title") == "Retention" for e in entries)
    assert any("oversized" in d for d in diagnostics)


@pytest.mark.asyncio
@pytest.mark.parametrize('body', [
    "15.6.4.\n503 Service Unavailable\nSkip to TOC\nThe server MAY send Retry-After.",
    "## 503 Service Unavailable\n\nThe server MAY send Retry-After.",
])
async def test_evaluator_search_advice_does_not_bypass_unread_local_section(body):
    from types import SimpleNamespace
    from deeptrace.domain import ResearchRequirement
    from deeptrace.strategies.evidence_evaluation import supplement_plan, missing_coverage
    from strategies.workflow.test_graph import _research_input

    fixture = build_gateway_fixture()
    record = await seed(fixture, 1, body)
    reqs = [ResearchRequirement(id="r1", description="RFC 9110 503 Retry-After")]
    state = {**_research_input("503 Retry-After"), "requirements": reqs, "evidence_contract_version": 3,
        "coverage": missing_coverage(reqs, "not_read"), "evidence_ids": [record.id],
        "source_eligibility": {record.id: "eligible"},
        "assessment": SimpleNamespace(recovery_tasks=[])}
    result = await supplement_plan(state, fixture.context, role="replanner", dispatched=[], limit=2, allow_reread=True)
    assert len(result["reread_actions"]) == 1
    read = result["reread_actions"][0]
    assert read.target_requirement_ids == ["r1"]
    assert "503 Service Unavailable" in body[read.anchor.start:read.anchor.end]
    assert "MAY send Retry-After" in body[read.anchor.start:read.anchor.end]
    state["read_anchors"] = [read.anchor]
    result = await supplement_plan(state, fixture.context, role="replanner", dispatched=[], limit=2, allow_reread=True)
    assert not result["reread_actions"]


@pytest.mark.asyncio
async def test_outline_includes_late_independent_tracks_within_existing_entry_budget():
    fixture = build_gateway_fixture()
    records = [await seed(fixture, i, f"Track {i} cancellation reference.") for i in range(16)]
    entries, blocks, _ = await build_source_outline(fixture.context, records, {}, max_entries=24)
    assert {b.anchor.evidence_id for b in blocks.values()} == {r.id for r in records}
    assert len(entries) <= 24


@pytest.mark.asyncio
async def test_compact_outline_keeps_late_gap_relevant_blocks_without_repeating_urls():
    fixture = build_gateway_fixture()
    body = "\n\n".join([f"Unrelated section {j}." for j in range(100)])
    body += "\n\nHOTEL_PRICE: twin room costs 400 per night."
    record = await seed(fixture, 1, body)
    entries, blocks, _ = await build_source_outline(
        fixture.context, [record], {}, focus_queries=["HOTEL_PRICE"], max_entries=24,
    )
    assert len(entries) <= 24
    assert "HOTEL_PRICE" in entries[0]["preview"]
    assert all("url" not in entry and "title" not in entry for entry in entries)
    assert set(blocks) == {entry["block_id"] for entry in entries}


@pytest.mark.asyncio
async def test_new_whole_read_has_room_despite_old_keyword_heavy_material():
    fixture = build_gateway_fixture()
    body = (
        "ordinary keyword. " * 350
        + "\n\n"
        + "NEW_CONDITION: the reader must finish before this can advance."
    )
    record = await seed(fixture, 1, body)
    start = body.index("NEW_CONDITION")
    old = ReadEvidenceAnchor(
        evidence_id=record.id,
        version=record.version,
        content_hash=record.content_hash,
        start=0,
        end=5000,
    )
    new = old.model_copy(update={"start": start, "end": len(body)})
    passages, _ = select_read_passages(
        record,
        body,
        [],
        [old, new],
        question="ordinary keyword",
        focus_queries=[],
        limit=3000,
        preferred_anchors=[new],
    )
    assert sum(len(p.text) for p in passages) <= 3000
    assert any(p.start <= start and p.end == len(body) for p in passages)
    assert "NEW_CONDITION" in "".join(p.text for p in passages)
    stale = new.model_copy(update={"content_hash": "wrong"})
    passages, issues = select_read_passages(
        record,
        body,
        [],
        [old],
        question="ordinary keyword",
        focus_queries=[],
        limit=3000,
        preferred_anchors=[stale],
    )
    assert "NEW_CONDITION" not in "".join(p.text for p in passages)
    assert "invalid_read_anchor" in issues


@pytest.mark.asyncio
async def test_reread_group_survives_global_budget_before_old_support_context():
    from deeptrace.domain import EvidenceSupport, Finding, ResearchRequirement
    from deeptrace.harness.token_budget import TokenBudgetConfig
    from deeptrace.strategies.evaluation_materials import (
        assemble_reference_evaluation_view,
    )

    fixture = build_gateway_fixture()
    body = (
        "ordinary keyword. " * 350
        + "\n\n"
        + "NEW_CONDITION: the reader must finish before this can advance."
    )
    record = await seed(fixture, 1, body)
    old = ReadEvidenceAnchor(
        evidence_id=record.id,
        version=record.version,
        content_hash=record.content_hash,
        start=0,
        end=5000,
    )
    new = old.model_copy(
        update={"start": body.index("NEW_CONDITION"), "end": len(body)}
    )
    support = EvidenceSupport(
        **old.model_dump(exclude={"queries", "end"}), end=17, quote=body[:17]
    )
    finding = Finding(
        id="f1",
        claim="Ordinary keyword.",
        evidence_ids=[record.id],
        supports=[support],
        confidence=0.8,
    )
    view = await assemble_reference_evaluation_view(
        fixture.context,
        question="ordinary keyword",
        requirements=[ResearchRequirement(id="r1", description="ordinary keyword")],
        evidence_ids=[record.id],
        findings=[finding],
        read_anchors=[old, new],
        preferred_read_anchors=[new],
        budget=TokenBudgetConfig(
            context_tokens=900, output_reserve_tokens=0, safety_tokens=0
        ),
    )
    assert "NEW_CONDITION" in view.prompt
    assert view.allocation.used_tokens <= 900
    assert any(
        p.start == new.start and p.end == new.end for p in view.references.values()
    )
