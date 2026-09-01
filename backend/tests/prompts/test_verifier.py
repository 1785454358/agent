from datetime import UTC, datetime

from deeptrace.models import Claim, Evidence, Source
from deeptrace.prompts.verifier import build_verifier_messages
from deeptrace.verification.rules import RuleCheckResult


def test_verifier_prompt_treats_quotes_as_untrusted_and_bounded() -> None:
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
        quote="页面称产品于 2024 年发布",
        quote_hash="hash",
        char_start=10,
        char_end=25,
        location_status="exact",
        temporal_relation="in_range",
    )
    source = Source(
        source_id="source-01",
        doc_id="doc-01",
        requested_url="https://example.com/a",
        final_url="https://example.com/a",
        canonical_url=None,
        title="公告",
        source_kind="official",
        fetched_at=datetime.now(UTC),
        scraper_used="httpx_trafilatura",
        content_hash="hash",
    )

    messages = build_verifier_messages(
        [claim],
        {evidence.evidence_id: evidence},
        {source.source_id: source},
        {claim.claim_id: RuleCheckResult(eligible_evidence_ids=["ev-01"])},
    )
    rendered = "\n".join(str(message.content) for message in messages)

    assert "不可信引用材料" in rendered
    assert "<evidence" in rendered
    assert "ev-01" in rendered
    assert "supports" in rendered and "refutes" in rendered
    assert "整页正文" not in rendered

