"""Independent audit retrieval must not be crowded out by accepted abstracts."""

import pytest

from deeptrace.domain import EvidenceSupport, Finding
from deeptrace.responses.evidence import assemble_response_materials
from responses.test_supported_findings import _case
from responses.test_graph import _seed_evidence
from strategies.fixtures import TENANT_ID


@pytest.mark.asyncio
async def test_audit_reserves_reading_space_beyond_large_accepted_opening():
    payload, _, fixture, _ = await _case()
    opening = ("Overview of the study and its contributions.\n\n" * 100)[:2000]
    protocol = "We set maximum generation length to 32,768 tokens and sampling temperature to 0.6."
    body = opening + "\n\n" + "Unrelated discussion.\n\n" * 500 + "## Evaluation protocol\n\n" + protocol
    ids = await _seed_evidence(fixture.evidence_store, [("https://example.com/paper", "Paper", body)])
    record = await fixture.evidence_store.get(TENANT_ID, ids[0])
    payload.question = "maximum generation length sampling temperature evaluation protocol"
    payload.research_outcome.evidence_ids = ids
    payload.research_outcome.findings = [Finding(id="f1", claim="Study overview", evidence_ids=ids,
        confidence=0.9, supports=[EvidenceSupport(evidence_id=record.id, version=record.version,
            content_hash=record.content_hash, start=a, end=a+500, quote=body[a:a+500])
            for a in range(0, 2000, 500)])]
    normal = await assemble_response_materials(fixture.context, payload, [record], 2000)
    assert protocol not in normal.sources[0]
    audit = await assemble_response_materials(fixture.context, payload, [record], 2000,
        max_support_chars=500)
    assert protocol in audit.sources[0]
    assert body[:500] in audit.sources[0]
    passages = audit.passages_by_source[record.id]
    assert sum(p.end-p.start for p in passages) <= 2000
    assert all(body[p.start:p.end] == p.text for p in passages)
