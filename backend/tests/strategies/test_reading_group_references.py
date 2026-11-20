"""Whole reads resolve only to current, visible, verbatim short citations."""

import json
from dataclasses import replace

import pytest
from pydantic import ValidationError

from deeptrace.domain import Finding, ResearchRequirement, ResearchTopicOutcome
from deeptrace.domain.evidence_anchor import ReadEvidenceAnchor
from deeptrace.harness.token_budget import TokenBudgetConfig, count_tokens
from deeptrace.strategies.evaluation_materials import assemble_reference_evaluation_view
from deeptrace.strategies.evidence_references import (
    ReferenceFindingDraft,
    ResearchResultDraft,
    normalize_reference_findings,
)
from strategies.fixtures import build_gateway_fixture
from strategies.test_reference_materials import seed


def draft(ref):
    return ReferenceFindingDraft(
        id="f1", claim="The result has explicit conditions.", confidence=0.8,
        supports=[{"ref": ref}],
    )


async def material(tokens=6000):
    fixture = build_gateway_fixture()
    body = "The result applies only to the stated conditions. " * 60
    record = await seed(fixture, 1, body)
    view = await assemble_reference_evaluation_view(
        fixture.context, question="result conditions", requirements=[],
        evidence_ids=[record.id], findings=[], read_anchors=[ReadEvidenceAnchor(
            evidence_id=record.id, version=record.version,
            content_hash=record.content_hash, start=0, end=len(body),
        )], budget=TokenBudgetConfig(
            context_tokens=tokens, output_reserve_tokens=0, safety_tokens=0,
        ),
    )
    return body, record, view


@pytest.mark.asyncio
async def test_one_group_resolves_more_than_three_short_quotes_exactly():
    body, record, view = await material()
    payload = json.loads(view.prompt.split("EVIDENCE_VIEW_JSON:\n", 1)[1])
    assert len(view.support_groups["g1"]) > 5
    assert payload["support_groups"][0] == {
        "ref": "g1", "source": "s1", "passages": list(view.support_groups["g1"]),
    }
    findings, issues = normalize_reference_findings(
        [draft("g1")], view.references, support_groups=view.support_groups,
    )
    assert not issues
    assert len(findings[0].supports) == len(view.support_groups["g1"])
    for support in findings[0].supports:
        assert support.evidence_id == record.id
        assert support.version == record.version
        assert support.content_hash == record.content_hash
        assert support.quote == body[support.start:support.end]
        assert len(support.quote) <= 500
    assert view.allocation.used_tokens == count_tokens(view.prompt)


@pytest.mark.asyncio
@pytest.mark.parametrize("mapping", [{}, {"g1": ()}, {"g1": ("p1", "p999")}])
async def test_unknown_or_incomplete_group_cannot_admit_partial_support(mapping):
    _, _, view = await material()
    findings, issues = normalize_reference_findings(
        [draft("g1")], view.references, support_groups=mapping,
    )
    assert findings == []
    assert "invalid_support_reference" in issues


@pytest.mark.asyncio
async def test_group_cannot_mix_source_versions():
    _, _, view = await material()
    refs = dict(view.references)
    refs["p2"] = replace(refs["p2"], version=refs["p2"].version + 1)
    findings, issues = normalize_reference_findings(
        [draft("g1")], refs, support_groups={"g1": ("p1", "p2")},
    )
    assert not findings and "invalid_support_reference" in issues


@pytest.mark.asyncio
async def test_dropped_material_has_no_group_reference():
    _, _, view = await material(tokens=0)
    payload = json.loads(view.prompt.split("EVIDENCE_VIEW_JSON:\n", 1)[1])
    assert not view.references and not view.support_groups
    assert not payload["support_groups"]
    findings, _ = normalize_reference_findings(
        [draft("g1")], view.references, support_groups=view.support_groups,
    )
    assert not findings


def test_publication_date_requires_a_specific_short_quote():
    with pytest.raises(ValidationError):
        ResearchResultDraft(
            kind="method", title="A result", published_on="2026-01-02",
            date_refs=[{"ref": "g1"}],
        )


@pytest.mark.asyncio
async def test_legacy_short_reference_still_resolves_and_deduplicates():
    _, _, view = await material()
    item = draft("p1")
    item.supports.append(item.supports[0])
    findings, issues = normalize_reference_findings([item], view.references)
    assert not issues and len(findings[0].supports) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("scientific", [False, True])
async def test_full_evaluator_admits_and_serializes_expanded_group(scientific):
    from langchain_core.messages import AIMessage

    from deeptrace.strategies.evidence_evaluation import run_evidence_evaluation
    from deeptrace.strategies.multi_agent.models import ReferenceSupervisorEvaluation

    class Gateway:
        async def invoke(self, *, messages, **kwargs):
            material = json.loads(messages[-1].content.split("EVIDENCE_VIEW_JSON:\n", 1)[1])
            assert len(material["support_groups"][0]["passages"]) > (3 if scientific else 5)
            item = draft("g1").model_dump(mode="json")
            findings = [item]
            if scientific:
                item["research_result"] = {"kind": "method", "title": "A result",
                    "published_on": "2026-01-02", "date_refs": [{"ref": "p1"}]}
                findings.append({**item, "id": "background", "research_result": {
                    **item["research_result"], "kind": "background"}})
            return AIMessage(content=json.dumps({
                "action": "complete", "reason": "Supported",
                "findings": findings,
                "coverage": {"items": [{"requirement_id": "r1", "status": "covered",
                    "finding_ids": ["f1"], "reason": "Conditions are visible"}]},
                "source_checks": [{"source": "s1", "status": "eligible", "reason": "No restriction"}],
            }))

    fixture = build_gateway_fixture(model_gateway=Gateway())
    body = ("Submitted on 2 Jan 2026.\n" if scientific else "") + "The result applies only to the stated conditions. " * 60
    record = await seed(fixture, 1, body)
    result = await run_evidence_evaluation({
        "run_id": "group-run", "thread_id": "group-thread", "question": "result conditions",
        "current_date": "2026-10-11", "timezone": "Asia/Shanghai",
        "evidence_contract_version": 3,
        "requirements": [ResearchRequirement(id="r1", description="result conditions")],
        "research_brief": {"source_policy": "research_results" if scientific else "general", "publication_years": [2026]},
        "evidence_ids": [record.id], "researcher_outcomes": [ResearchTopicOutcome(
            query="result", evidence_ids=[record.id], read_anchors=[ReadEvidenceAnchor(
                evidence_id=record.id, version=record.version, content_hash=record.content_hash,
                start=0, end=len(body),
            )],
        )],
    }, fixture.context, ReferenceSupervisorEvaluation, incomplete_action="follow_up")
    assert result["coverage"].items[0].status == "covered"
    assert result["source_eligibility"][record.id] == "eligible"
    finding = result["findings"][0]
    assert len(finding.supports) > (3 if scientific else 5)
    assert Finding.model_validate_json(finding.model_dump_json()) == finding
    assert result["unresolved_gaps"] == []
    if scientific:
        assert "invalid_research_result:background" in result["diagnostic_gaps"]


@pytest.mark.asyncio
@pytest.mark.parametrize("claimed_date, accepted", [("2026-01-02", True), ("2026-01-03", False)])
async def test_group_references_keep_exact_scientific_date_validation(claimed_date, accepted):
    fixture = build_gateway_fixture()
    body = "Submitted on 2 Jan 2026.\nWe introduce a method with limited conditions. " * 40
    record = await seed(fixture, 1, body)
    view = await assemble_reference_evaluation_view(
        fixture.context, question="method", requirements=[], evidence_ids=[record.id],
        findings=[], read_anchors=[ReadEvidenceAnchor(evidence_id=record.id,
            version=record.version, content_hash=record.content_hash, start=0, end=len(body))],
        prefer_research_passages=True,
    )
    item = draft("g1")
    item.research_result = ResearchResultDraft(kind="method", title="A limited method",
        published_on=claimed_date, date_refs=[{"ref": "p1"}])
    findings, issues = normalize_reference_findings([item], view.references,
        source_policy="research_results", publication_years=[2026], support_groups=view.support_groups)
    assert bool(findings) is accepted
    assert ("invalid_research_result:f1" in issues) is not accepted
