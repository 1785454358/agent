from datetime import date
from types import SimpleNamespace

import pytest

from deeptrace.agent.claim_extractor import (
    ClaimDraft,
    ClaimExtractorAgent,
    fallback_claims,
    materialize_claims,
    parse_claim_output,
)
from deeptrace.models import Evidence, ResearchTimeRange


def _evidence(evidence_id: str, *, exact: bool = True) -> Evidence:
    return Evidence(
        evidence_id=evidence_id,
        source_id="source-01",
        doc_id="doc-01",
        note_id="note-01",
        task_id="task-01",
        section_id="section-01",
        quote="原文摘录",
        quote_hash=f"hash-{evidence_id}",
        char_start=0 if exact else None,
        char_end=4 if exact else None,
        location_status="exact" if exact else "unlocated",
        temporal_relation="in_range",
    )


def test_parse_claim_output_repairs_embedded_json() -> None:
    output = parse_claim_output(
        'prefix {"claims": [{"text": "发布了新模型", "kind": "factual", '
        '"importance": "key", "evidence_ids": ["ev-01"]}]} suffix'
    )

    assert output.claims[0].text == "发布了新模型"


def test_materialize_removes_unknown_and_unlocated_evidence(
    research_task,
) -> None:
    exact = _evidence("ev-exact")
    unlocated = _evidence("ev-unlocated", exact=False)
    draft = ClaimDraft(
        text="2024 年发布了新模型",
        kind="temporal",
        importance="key",
        event_start_date=date(2025, 1, 1),
        evidence_ids=["ev-exact", "ev-unlocated", "ev-missing"],
    )

    claims = materialize_claims(
        drafts=[draft],
        evidence={
            exact.evidence_id: exact,
            unlocated.evidence_id: unlocated,
        },
        task=research_task,
        time_range=ResearchTimeRange(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
        ),
    )

    assert claims[0].evidence_ids == ["ev-exact"]
    assert claims[0].event_start == date(2025, 1, 1)


def test_fallback_key_points_are_not_verified(research_note) -> None:
    exact = _evidence("ev-exact")

    claims = fallback_claims([research_note], [exact])

    assert claims[0].importance == "supporting"
    assert claims[0].evidence_ids == [exact.evidence_id]


@pytest.mark.anyio
async def test_two_malformed_responses_use_deterministic_fallback(
    research_task, research_note
) -> None:
    class MalformedModel:
        calls = 0

        async def ainvoke(self, _messages):
            self.calls += 1
            return SimpleNamespace(
                content="不是 JSON",
                usage_metadata={
                    "input_tokens": 2,
                    "output_tokens": 1,
                    "total_tokens": 3,
                },
            )

    model = MalformedModel()
    agent = ClaimExtractorAgent(model)
    claims, usage, used_fallback = await agent.aextract(
        research_task,
        [research_note],
        [_evidence("ev-exact")],
        None,
    )

    assert model.calls == 2
    assert used_fallback is True
    assert claims[0].importance == "supporting"
    assert usage.total_tokens == 6

