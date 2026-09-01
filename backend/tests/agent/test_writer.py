from deeptrace.agent.writer import (
    find_unqualified_year_mentions,
    is_language_consistent,
    parse_writer_output,
    render_fallback_report,
)
from deeptrace.prompts.writer import build_writer_messages


def test_writer_quality_validators() -> None:
    assert not is_language_consistent("Only English text about agents.", "zh-CN")
    assert is_language_consistent("这是关于智能体领域的重要进展报告。", "zh-CN")
    assert find_unqualified_year_mentions(
        "OpenAI Presence 于 2026 年发布。", 2024, 2024
    ) == [2026]
    assert find_unqualified_year_mentions(
        "后续回顾：Presence 于 2026 年发布，不属于 2024 年进展。", 2024, 2024
    ) == []


def test_writer_messages_do_not_contain_raw_document(
    research_plan, section_result, research_note
) -> None:
    messages = build_writer_messages(
        plan=research_plan,
        sections=[section_result],
        notes=[research_note],
        termination_reason="completed",
    )
    text = "\n".join(str(message.content) for message in messages)

    assert research_note.key_points[0] in text
    assert "整页正文唯一标记" not in text


def test_fallback_report_discloses_partial_sections(
    research_plan, partial_section, research_note
) -> None:
    output = render_fallback_report(
        research_plan,
        [partial_section],
        [research_note],
        "token_budget",
    )

    assert "部分完成" in output.markdown
    assert "token_budget" in output.markdown
    assert output.used_note_ids == [research_note.note_id]


def test_writer_parses_fenced_json_without_provider_specific_parameters() -> None:
    output = parse_writer_output(
        """```json
        {"markdown": "# 报告\\n\\n内容", "used_note_ids": ["note-01"]}
        ```"""
    )

    assert output.markdown.startswith("# 报告")
    assert output.used_note_ids == ["note-01"]
