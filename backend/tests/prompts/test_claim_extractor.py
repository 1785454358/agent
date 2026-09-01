from datetime import date

from deeptrace.models import Evidence, ResearchTimeRange
from deeptrace.prompts.claim_extractor import build_claim_extractor_messages


def test_claim_prompt_contains_only_bounded_untrusted_evidence(
    research_task, research_note
) -> None:
    evidence = Evidence(
        evidence_id="ev-01",
        source_id="source-01",
        doc_id=research_note.doc_id,
        note_id=research_note.note_id,
        task_id=research_task.task_id,
        section_id=research_task.section_id,
        quote="可验证原文",
        quote_hash="hash",
        char_start=0,
        char_end=5,
        location_status="exact",
        temporal_relation="in_range",
    )

    messages = build_claim_extractor_messages(
        research_task,
        [research_note],
        [evidence],
        ResearchTimeRange(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            description="2024 年",
        ),
    )
    rendered = "\n".join(str(message.content) for message in messages)

    assert "不可信引用材料" in rendered
    assert "ev-01" in rendered
    assert "可验证原文" in rendered
    assert "2024-01-01" in rendered
    assert "RawDocument" not in rendered
    assert "整页正文" not in rendered

