"""Only visible host read references may become bounded candidate findings."""

import importlib
import importlib.util
import json
from dataclasses import asdict

import pytest
from deeptrace.domain import ResearchMode
from deeptrace.tools.evidence_views import make_evidence_passage
from pydantic import ValidationError
from strategies.fixtures import build_gateway_fixture

from harness.test_record_findings_loop import seed, task_for


def module():
    assert importlib.util.find_spec("deeptrace.harness.research_findings") is not None
    return importlib.import_module("deeptrace.harness.research_findings")


def preview(record, body):
    return json.dumps(
        {
            "evidence_id": record.id,
            "version": record.version,
            "content_hash": record.content_hash,
            "historical": False,
            "selection": {"body_length": len(body), "omitted": False},
            "passages": [asdict(make_evidence_passage(record, body, 0, len(body)))],
        }
    )


@pytest.mark.asyncio
async def test_numbering_is_visible_stable_and_registry_has_no_body():
    fixture = build_gateway_fixture()
    record, body = await seed(fixture)
    raw = preview(record, body)
    rendered, refs, diagnostics = module().number_read_preview(raw, {})
    assert list(refs) == ["n1"]
    assert json.loads(rendered)["passages"][0]["text"] == body
    assert json.loads(rendered)["passages"][0]["ref"] == "n1"
    assert "quote" not in refs["n1"].model_dump()
    again, same, _ = module().number_read_preview(raw, refs)
    assert again == rendered and same == refs
    assert not diagnostics
    _, empty, issues = module().number_read_preview(raw[:-1], {})
    assert empty == {} and issues


@pytest.mark.asyncio
async def test_record_is_raw_supported_idempotent_and_batch_atomic():
    fixture = build_gateway_fixture()
    record, body = await seed(fixture)
    api = module()
    _, refs, _ = api.number_read_preview(preview(record, body), {})
    args = api.RecordFindingsArguments(
        findings=[{"claim": "Context key required.", "refs": ["n1"], "confidence": 0.9}]
    )
    kwargs = {
        "task": task_for(ResearchMode.WORKFLOW, record),
        "references": refs,
        "context": fixture.context,
    }
    first = await api.resolve_recorded_findings(args, existing=[], **kwargs)
    assert len(first) == 1
    assert first[0].supports[0].quote == body
    assert first[0].supports[0].end == len(body)
    assert await api.resolve_recorded_findings(args, existing=first, **kwargs) == first
    bad = api.RecordFindingsArguments(
        findings=[
            args.findings[0],
            {"claim": "Invented", "refs": ["n99"], "confidence": 1},
        ]
    )
    with pytest.raises(ValueError, match="invalid_read_reference"):
        await api.resolve_recorded_findings(bad, existing=first, **kwargs)
    assert len(first) == 1
    with pytest.raises(ValueError, match="evidence_not_authorized"):
        await api.resolve_recorded_findings(
            args,
            existing=[],
            **{
                **kwargs,
                "task": kwargs["task"].model_copy(
                    update={"authorized_evidence_ids": []}
                ),
            },
        )


@pytest.mark.asyncio
async def test_escaped_preview_registers_only_whole_surviving_units():
    fixture = build_gateway_fixture()
    record, _ = await seed(fixture)
    body = '\\"\n🙂' * 750
    rendered, refs, _ = module().number_read_preview(preview(record, body), {})
    payload = json.loads(rendered)
    assert len(rendered) <= 4000
    assert len(refs) == len(payload["passages"])
    assert payload["selection"]["omitted"]
    # An oversized original reading group is omitted whole, not half retained.
    assert not refs
    for p in payload["passages"]:
        assert len(p["text"]) <= 500
        assert p["text"] == body[p["start"] : p["end"]]


@pytest.mark.parametrize("values", [[], ["p1"], ["n0"], ["n1", "n1"], ["n1"] * 4])
def test_record_refs_are_bounded_and_distinct(values):
    with pytest.raises(ValidationError):
        module().RecordFindingDraft(claim="Claim", refs=values, confidence=0.8)


@pytest.mark.asyncio
async def test_capacity_stale_source_and_inputs_remain_atomic():
    fixture = build_gateway_fixture()
    record, body = await seed(fixture)
    api = module()
    _, refs, _ = api.number_read_preview(preview(record, body), {})
    before = dict(refs)
    full = {
        f"n{i}": refs["n1"].model_copy(update={"start": i + 100, "end": i + 101})
        for i in range(1, 129)
    }
    rendered, retained, issues = api.number_read_preview(preview(record, body), full)
    assert not json.loads(rendered)["passages"]
    assert retained == full and "read_reference_capacity" in issues
    args = api.RecordFindingsArguments(
        findings=[{"claim": "Claim", "refs": ["n1"], "confidence": 0.8}]
    )
    kwargs = {
        "task": task_for(ResearchMode.WORKFLOW, record),
        "context": fixture.context,
    }
    with pytest.raises(ValueError, match="invalid_read_reference_source"):
        await api.resolve_recorded_findings(
            args,
            references={"n1": refs["n1"].model_copy(update={"version": 99})},
            existing=[],
            **kwargs,
        )
    first = await api.resolve_recorded_findings(
        args, references=refs, existing=[], **kwargs
    )
    existing = [first[0].model_copy(update={"id": f"research-{i}"}) for i in range(20)]
    with pytest.raises(ValueError, match="research_finding_capacity"):
        await api.resolve_recorded_findings(
            args, references=refs, existing=existing, **kwargs
        )
    assert len(existing) == 20 and refs == before
