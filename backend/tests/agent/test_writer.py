import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from deeptrace.agent.writer import (
    ReportBlock,
    VerifiedReportSection,
    VerifiedWriterOutput,
    WriterAgent,
    find_unqualified_year_mentions,
    is_language_consistent,
    render_verified_output,
    sources_from_used_claims,
    validate_writer_output,
)
from deeptrace.models import Claim, Evidence, Source, VerificationResult


def test_writer_quality_validators() -> None:
    assert not is_language_consistent("Only English text about agents.", "zh-CN")
    assert is_language_consistent("这是关于智能体领域的重要进展报告。", "zh-CN")
    assert find_unqualified_year_mentions(
        "OpenAI Presence 于 2026 年发布。", 2024, 2024
    ) == [2026]
    assert find_unqualified_year_mentions(
        "后续回顾：Presence 于 2026 年发布，不属于 2024 年进展。",
        2024,
        2024,
    ) == []


def _lineage(verdict: str = "verified"):
    claim = Claim(
        claim_id="claim-01",
        task_id="task-01",
        section_id="section-01",
        text="产品在 2024 年发布",
        kind="temporal",
        importance="key",
        evidence_ids=["ev-01"],
    )
    evidence = Evidence(
        evidence_id="ev-01",
        source_id="source-01",
        doc_id="doc-01",
        note_id="note-01",
        task_id="task-01",
        section_id="section-01",
        quote="产品于 2024 年正式发布。",
        quote_hash="hash",
        char_start=0,
        char_end=13,
        location_status="exact",
        temporal_relation="in_range",
    )
    source = Source(
        source_id="source-01",
        doc_id="doc-01",
        requested_url="https://example.com/release",
        final_url="https://example.com/release",
        canonical_url=None,
        title="正式公告",
        source_kind="official",
        fetched_at=datetime.now(UTC),
        scraper_used="httpx_trafilatura",
        content_hash="hash",
    )
    result = VerificationResult(
        claim_id=claim.claim_id,
        verdict=verdict,
        reason="核验完成",
        supporting_evidence_ids=[evidence.evidence_id],
        verified_at=datetime.now(UTC),
    )
    return claim, evidence, source, result


def _output(claim_id: str) -> VerifiedWriterOutput:
    return VerifiedWriterOutput(
        title="报告",
        sections=[
            VerifiedReportSection(
                heading="进展",
                blocks=[
                    ReportBlock(
                        kind="fact",
                        text="产品发布",
                        claim_ids=[claim_id],
                    )
                ],
            )
        ],
        used_claim_ids=[claim_id],
    )


def test_writer_rejects_unsupported_claim_id() -> None:
    claim, _evidence, _source, result = _lineage("unsupported")

    violations = validate_writer_output(
        _output(claim.claim_id), {claim.claim_id: result}
    )

    assert "claim_not_writable" in violations


def test_renderer_resolves_claim_to_exact_source() -> None:
    claim, evidence, source, result = _lineage()

    markdown = render_verified_output(
        _output(claim.claim_id),
        {claim.claim_id: claim},
        {claim.claim_id: result},
        {evidence.evidence_id: evidence},
        {source.source_id: source},
    )

    assert "[[claim:" not in markdown
    assert source.final_url in markdown
    assert evidence.quote in markdown


def test_sources_only_include_used_claims() -> None:
    claim, evidence, source, _result = _lineage()

    assert sources_from_used_claims(
        [claim.claim_id],
        {claim.claim_id: claim},
        {evidence.evidence_id: evidence},
        {source.source_id: source},
    ) == [source.final_url]


@pytest.mark.anyio
async def test_writer_retries_unsupported_then_accepts_verified(
    research_plan, section_result
) -> None:
    claim, evidence, source, verified = _lineage()
    unsupported = verified.model_copy(
        update={"claim_id": "claim-bad", "verdict": "unsupported"}
    )

    class Model:
        calls = 0

        async def ainvoke(self, _messages):
            self.calls += 1
            claim_id = "claim-bad" if self.calls == 1 else claim.claim_id
            return SimpleNamespace(
                content=json.dumps(
                    {
                        "title": "报告",
                        "sections": [
                            {
                                "heading": "进展",
                                "blocks": [
                                    {
                                        "kind": "fact",
                                        "text": "产品发布",
                                        "claim_ids": [claim_id],
                                    }
                                ],
                            }
                        ],
                        "used_claim_ids": [claim_id],
                    },
                    ensure_ascii=False,
                ),
                usage_metadata={"total_tokens": 2},
            )

    model = Model()
    agent = WriterAgent(model)
    output, usage, fallback = await agent.awrite(
        plan=research_plan,
        sections=[section_result],
        claims=[claim],
        verification_results={
            claim.claim_id: verified,
            "claim-bad": unsupported,
        },
        evidence={evidence.evidence_id: evidence},
        sources={source.source_id: source},
        gaps=[],
        termination_reason="completed",
    )

    assert model.calls == 2
    assert output.used_claim_ids == [claim.claim_id]
    assert usage.total_tokens == 4
    assert fallback is False


@pytest.mark.anyio
async def test_writer_falls_back_without_verified_claims(
    research_plan, section_result
) -> None:
    claim, evidence, source, result = _lineage("unsupported")
    agent = WriterAgent(SimpleNamespace())

    output, usage, fallback = await agent.awrite(
        plan=research_plan,
        sections=[section_result],
        claims=[claim],
        verification_results={claim.claim_id: result},
        evidence={evidence.evidence_id: evidence},
        sources={source.source_id: source},
        gaps=[],
        termination_reason="completed",
    )

    assert fallback is True
    assert output.used_claim_ids == []
    assert usage.total_tokens == 0
    assert output.sections[0].blocks[0].kind == "limitation"
