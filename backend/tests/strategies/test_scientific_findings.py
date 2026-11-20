from datetime import date

import pytest

from deeptrace.strategies.evidence_references import (
    ReferenceFindingDraft,
    normalize_reference_findings,
)
from deeptrace.tools.evidence_views import EvidencePassage


def resolve(
    kind="original_experiment",
    published="2026-06-27",
    date_text="Published: 27 June 2026",
    years=(2026,),
):
    text = date_text + ". We observed long-range coherence in attractive Bose gases."
    passage = EvidencePassage(
        passage_id="p-test",
        evidence_id="evidence-test",
        version=1,
        content_hash="sha256:" + "a" * 64,
        start=0,
        end=len(text),
        start_line=1,
        end_line=1,
        text=text,
    )
    draft = ReferenceFindingDraft.model_validate(
        {
            "id": "finding-1",
            "claim": "Long-range coherence was measured in attractive Bose gases.",
            "confidence": 0.9,
            "supports": [{"ref": "p1"}],
            "research_result": {
                "kind": kind,
                "title": "Coherence in attractive Bose gases",
                "published_on": published,
                "date_refs": ["p1"],
            },
        }
    )
    return normalize_reference_findings(
        [draft],
        {"p1": passage},
        source_policy="research_results",
        publication_years=list(years),
        cutoff=date(2026, 10, 6),
    )


def test_grounded_original_result_is_admitted():
    findings, issues = resolve()
    assert len(findings) == 1 and not issues


@pytest.mark.parametrize("kind", ["review", "background", "unknown"])
def test_review_or_background_cannot_complete_original_research(kind):
    findings, issues = resolve(kind=kind)
    assert not findings and issues


def test_old_publication_is_not_admitted_as_current_year_progress():
    findings, issues = resolve(published="2025-02-10", date_text="February 10, 2025")
    assert not findings and issues


def test_footer_year_is_not_a_publication_date():
    findings, issues = resolve(date_text="Copyright 2026. All rights reserved.")
    assert not findings and issues


def test_news_dateline_cannot_establish_original_research_publication_year():
    findings, issues = resolve(
        published="2026-02-08",
        date_text="Date: February 8, 2026. Source: University. Journal Reference: Published 6 November 2025",
    )
    assert not findings and issues


def test_news_html_publication_date_is_not_original_paper_publication_date():
    findings, issues = resolve(
        published='2026-06-27',
        date_text='Source type (HTML metadata): NewsArticle\nPublished (HTML metadata): 2026-06-27\n'
                  'Journal reference: Published 6 November 2025',
    )
    assert not findings and issues


@pytest.mark.asyncio
async def test_originals_from_every_branch_reach_the_bounded_global_evaluator():
    import json

    from deeptrace.domain import ResearchRequirement, ResearchTopicOutcome
    from deeptrace.domain.evidence_anchor import ReadEvidenceAnchor
    from deeptrace.strategies.evidence_evaluation import run_evidence_evaluation
    from deeptrace.strategies.plan_execute.models import ReferenceExecutorDecision
    from deeptrace.tools.evidence_store import EvidenceDraft
    from strategies.fixtures import (
        FIXED_NOW,
        ScriptedModelGateway,
        build_gateway_fixture,
    )

    captured = {}
    def evaluate(prompt):
        captured.update(json.loads(prompt.split('EVIDENCE_VIEW_JSON:\n')[1]))
        return 'invalid'  # Only source selection is under test, not model judgment.
    fixture = build_gateway_fixture(model_gateway=ScriptedModelGateway({'evaluator': evaluate}))
    reports, originals, outcomes = [], [], []
    for branch in range(3):
        ids, anchors = [], []
        for kind in ('report', 'primary-a', 'primary-b'):
            body = f'Published: 4 May 2026\nOriginal experiment {branch} {kind}.'
            record = await fixture.evidence_store.ingest('workspace-1', EvidenceDraft(
                canonical_url=f'https://example.com/{branch}/{kind}', title=kind, media_type='text/plain',
                body=body, fetched_at=FIXED_NOW, source_quality=0.9))
            ids.append(record.id)
            if kind == 'report':
                reports.append(record.id)
            else:
                originals.append(record.id)
                anchors.append(ReadEvidenceAnchor(evidence_id=record.id, version=record.version,
                    content_hash=record.content_hash, start=0, end=len(body)))
        outcomes.append(ResearchTopicOutcome(query=f'branch-{branch}', evidence_ids=ids, read_anchors=anchors))
    await run_evidence_evaluation({
        'run_id':'run-1', 'thread_id':'thread-1', 'question':'Three research directions',
        'current_date':'2026-10-06', 'timezone':'Asia/Shanghai', 'evidence_contract_version':3,
        'requirements':[ResearchRequirement(id='r1', description='Representative results across directions')],
        'research_brief':{'source_policy':'research_results','publication_years':[2026]},
        'evidence_ids':[*reports,*originals], 'topic_outcomes':outcomes,
    }, fixture.context, ReferenceExecutorDecision)
    assert {s['url'] for s in captured['sources']} >= {
        f'https://example.com/{b}/{kind}' for b in range(3) for kind in ('primary-a','primary-b')
    }


def test_future_publication_is_not_admitted():
    findings, issues = resolve(
        published="2026-12-01", date_text="Published: 1 December 2026"
    )
    assert not findings and issues


def test_fabricated_date_cannot_be_supported_by_old_visible_text():
    findings, issues = resolve(date_text="Published: 27 June 2025")
    assert not findings and issues


def test_received_and_accepted_do_not_hide_the_following_publication_date():
    findings, issues = resolve(
        date_text="Received: 2 May 2026. Accepted: 12 June 2026. Published: 27 June 2026"
    )
    assert len(findings) == 1 and not issues


def test_arxiv_submission_with_abbreviated_month_is_supported():
    findings, issues = resolve(
        published="2026-03-10", date_text="Submitted on 10 Mar 2026"
    )
    assert len(findings) == 1 and not issues


def test_date_references_use_the_same_object_shape_as_contribution_references():
    draft = ReferenceFindingDraft.model_validate(
        {
            "id": "f1",
            "claim": "claim",
            "confidence": 1,
            "supports": [{"ref": "p1"}],
            "research_result": {
                "kind": "method",
                "title": "Method",
                "published_on": "2026-06-27",
                "date_refs": [{"ref": "p1"}],
            },
        }
    )
    assert draft.research_result.date_refs[0].ref == "p1"


def test_perspective_article_is_not_relabelled_as_an_original_method():
    findings, issues = resolve(
        kind="method",
        date_text="Published: 27 June 2026. Abstract: This perspective article analyzes existing methods",
    )
    assert not findings and issues


def test_date_reference_is_preserved_alongside_three_contribution_references():
    refs = {}
    for i, text in enumerate(
        [
            "Contribution A.",
            "Contribution B.",
            "Contribution C.",
            "Published: 27 June 2026",
        ],
        1,
    ):
        refs[f"p{i}"] = EvidencePassage(
            "source", 1, "hash", f"unit-{i}", i * 100, i * 100 + len(text), 1, 1, text
        )
    draft = ReferenceFindingDraft.model_validate(
        {
            "id": "f1",
            "claim": "Contributions A, B, and C.",
            "confidence": 1,
            "supports": [{"ref": f"p{i}"} for i in range(1, 4)],
            "research_result": {
                "kind": "method",
                "title": "A new method",
                "published_on": "2026-06-27",
                "date_refs": ["p4"],
            },
        }
    )
    findings, issues = normalize_reference_findings(
        [draft],
        refs,
        source_policy="research_results",
        publication_years=[2026],
        cutoff=date(2026, 10, 6),
    )
    assert len(findings) == 1 and not issues
    assert len(findings[0].supports) == 4
    assert findings[0].supports[-1].quote == "Published: 27 June 2026"


@pytest.mark.asyncio
async def test_background_claim_cannot_complete_coverage_or_enter_writer_sources():
    import json

    from deeptrace.domain import ResearchRequirement
    from deeptrace.strategies.evidence_evaluation import run_evidence_evaluation
    from deeptrace.strategies.plan_execute.models import ReferenceExecutorDecision
    from deeptrace.tools.evidence_store import EvidenceDraft
    from strategies.fixtures import (
        FIXED_NOW,
        ScriptedModelGateway,
        build_gateway_fixture,
    )

    def evaluate(prompt):
        view = json.loads(prompt.split("EVIDENCE_VIEW_JSON:\n")[1])
        ref = view["passages"][0]["ref"]
        return json.dumps(
            {
                "action": "complete",
                "reason": "complete",
                "unresolved_gaps": [],
                "findings": [
                    {
                        "id": "f1",
                        "claim": "A conference happened.",
                        "confidence": 1,
                        "supports": [{"ref": ref}],
                        "research_result": {
                            "kind": "background",
                            "title": "Conference",
                            "published_on": "2026-06-27",
                            "date_refs": [ref],
                        },
                    }
                ],
                "coverage": {
                    "items": [
                        {
                            "requirement_id": "r1",
                            "status": "covered",
                            "reason": "conference",
                            "finding_ids": ["f1"],
                        }
                    ]
                },
                "source_checks": [
                    {"source": "s1", "status": "eligible", "reason": "official"}
                ],
            }
        )

    fixture = build_gateway_fixture(
        model_gateway=ScriptedModelGateway({"evaluator": evaluate})
    )
    record = await fixture.evidence_store.ingest(
        "workspace-1",
        EvidenceDraft(
            canonical_url="https://example.com/conference",
            title="Conference",
            media_type="text/plain",
            body="Published: 27 June 2026. A conference happened.",
            fetched_at=FIXED_NOW,
            source_quality=1,
        ),
    )
    result = await run_evidence_evaluation(
        {
            "run_id": "run-1",
            "thread_id": "thread-1",
            "question": "Research progress",
            "current_date": "2026-09-12",
            "timezone": "UTC",
            "evidence_ids": [record.id],
            "evidence_contract_version": 3,
            "requirements": [
                ResearchRequirement(id="r1", description="Original result")
            ],
            "research_brief": {
                "source_policy": "research_results",
                "publication_years": [2026],
            },
        },
        fixture.context,
        ReferenceExecutorDecision,
        incomplete_action="replan",
    )
    assert result["findings"] == []
    assert result["coverage"].items[0].status == "missing"
    assert result["assessment"].action == "replan"
    assert result["source_eligibility"][record.id] == "ineligible"


@pytest.mark.asyncio
async def test_scientific_view_exposes_only_publication_dates_with_visible_refs():
    import json

    from deeptrace.domain import ResearchRequirement
    from deeptrace.strategies.evaluation_materials import (
        assemble_reference_evaluation_view,
    )
    from deeptrace.tools.evidence_store import EvidenceDraft
    from strategies.fixtures import FIXED_NOW, build_gateway_fixture

    fixture = build_gateway_fixture()
    record = await fixture.evidence_store.ingest(
        "workspace-1",
        EvidenceDraft(
            canonical_url="https://example.com/paper",
            title="Original experiment",
            media_type="text/plain",
            body="Received: 1 January 2025. Published: 27 June 2026.\nWe observe a new phase.",
            fetched_at=FIXED_NOW,
            source_quality=1,
        ),
    )
    view = await assemble_reference_evaluation_view(
        fixture.context,
        question="Research progress",
        requirements=[ResearchRequirement(id="r1", description="Original experiment")],
        evidence_ids=[record.id],
        findings=[],
        read_anchors=[],
        prefer_research_passages=True,
    )
    payload = json.loads(view.prompt.split("EVIDENCE_VIEW_JSON:\n")[1])
    dates = payload["publication_dates"]
    assert len(dates) == 1
    assert dates[0]["published_on"] == "2026-06-27"
    assert dates[0]["source"] == "s1"
    assert all(ref["ref"] in view.references for ref in dates[0]["date_refs"])
    assert "Published: 27 June 2026" in view.references[dates[0]["date_refs"][0]["ref"]].text
