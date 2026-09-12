import pytest
from pydantic import ValidationError

from deeptrace.domain import ResponseMode
from deeptrace.responses.citations import (
    extract_citation_markers,
    validate_citations,
)
from deeptrace.responses.models import ResponseDraft


def test_select_response_mode_defaults_to_answer() -> None:
    from deeptrace.responses.citations import select_response_mode

    assert select_response_mode("这份报告的作者是谁？") is ResponseMode.ANSWER
    assert select_response_mode("LangGraph 的 checkpoint 存在哪里") is ResponseMode.ANSWER
    assert select_response_mode("report 这个单词是什么意思") is ResponseMode.ANSWER
    assert select_response_mode(
        "checkpoint 和 store 有什么区别"
    ) is ResponseMode.ANSWER
    assert select_response_mode("自动生成的报告是什么") is ResponseMode.ANSWER


def test_select_response_mode_explicit_commands() -> None:
    from deeptrace.responses.citations import select_response_mode

    for request in (
        "生成报告",
        "请写一份报告",
        "输出完整报告",
        "给我一份正式报告",
        "请以报告形式输出",
        "generate a report on LangGraph",
        "write me a full report",
    ):
        assert select_response_mode(request) is ResponseMode.REPORT, request

    for request in (
        "整理成简报",
        "输出一份简报",
        "帮我总结成结构化摘要",
        "总结一下上文的要点可以吗",
        "give me a brief summary",
    ):
        assert select_response_mode(request) is ResponseMode.BRIEF, request


def test_response_draft_is_bounded() -> None:
    draft = ResponseDraft(response_mode=ResponseMode.ANSWER, content="回答内容 [1]")
    assert draft.content.endswith("[1]")
    with pytest.raises(ValidationError):
        ResponseDraft(response_mode=ResponseMode.ANSWER, content="   ")
    with pytest.raises(ValidationError):
        ResponseDraft(response_mode=ResponseMode.ANSWER, content="x" * 100_000)


def test_extract_citation_markers_returns_stable_order() -> None:
    markers = extract_citation_markers("前文 [2] 和 [1]，以及 [2] 重复。")
    assert markers == ["[2]", "[1]"]
    assert extract_citation_markers("没有引用") == []


def test_validate_citations_keeps_loaded_and_removes_unknown() -> None:
    draft = ResponseDraft(
        response_mode=ResponseMode.ANSWER,
        content="资料说明 [1]，补充 [2]，未知来源 [7]，重复 [1]。",
    )

    outcome = validate_citations(
        draft, loaded_evidence_ids=["evidence-a", "evidence-b"]
    )

    assert outcome.response_mode is ResponseMode.ANSWER
    assert outcome.partial_reason is None
    assert [citation.evidence_id for citation in outcome.citations] == [
        "evidence-a",
        "evidence-b",
    ]
    assert [citation.marker for citation in outcome.citations] == ["[1]", "[2]"]
    assert outcome.cited_evidence_ids == ["evidence-a", "evidence-b"]
    assert "[7]" not in outcome.content
    assert "未知来源" in outcome.content


def test_validate_citations_without_loaded_sources_yields_partial() -> None:
    draft = ResponseDraft(
        response_mode=ResponseMode.REPORT,
        content="看似完整的报告 [1]。",
    )

    outcome = validate_citations(draft, loaded_evidence_ids=[])

    assert outcome.citations == []
    assert outcome.cited_evidence_ids == []
    assert outcome.partial_reason == "no_supported_citations"
