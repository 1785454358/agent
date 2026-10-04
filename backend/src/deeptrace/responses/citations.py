"""Deterministic response-mode selection and citation validation policy."""

from __future__ import annotations

import re

from deeptrace.domain import CitationRef, ResponseMode, ResponseOutcome
from deeptrace.responses.models import ResponseDraft

_MAX_RESPONSE_INPUT_CHARS = 500

_REPORT_TAIL_FORMS = ("报告形式", "报告格式", "完整报告", "正式报告")
_BRIEF_WORDS = (
    "总结",
    "摘要",
    "简报",
    "对比",
    "归纳",
    "要点",
    "brief",
    "summary",
    "tldr",
)
_REPORT_VERB_PATTERN = re.compile(
    r"\b(generate|write|produce|create|draft)\b[\s\S]{0,20}\breport\b",
    re.IGNORECASE,
)


def select_response_mode(user_input: str) -> ResponseMode:
    """Boundary policy: only explicit report/brief wording changes output form."""
    text = (user_input or "").strip()[:_MAX_RESPONSE_INPUT_CHARS]
    lowered = text.lower()
    stripped = lowered.rstrip("。！？!? \t\n吧呗了")

    if (
        any(form in text for form in _REPORT_TAIL_FORMS)
        or stripped.endswith("报告")
        or stripped.endswith("report")
        or _REPORT_VERB_PATTERN.search(lowered) is not None
    ):
        return ResponseMode.REPORT
    if any(word in lowered for word in _BRIEF_WORDS):
        return ResponseMode.BRIEF
    return ResponseMode.ANSWER


_MARKER_PATTERN = re.compile(r"\[(\d{1,3})\]")
# 中文模型常见的异体角标：【1】、［1］ 统一按半角 [1] 处理。
_ALT_MARKER_PATTERN = re.compile(r"[［【]\s*(\d{1,3})\s*[】］]")


def normalize_citation_brackets(content: str) -> str:
    """Normalize full-width / lenticular citation brackets to ASCII [n]."""
    if not content:
        return content or ""
    return _ALT_MARKER_PATTERN.sub(lambda match: f"[{match.group(1)}]", content)


def extract_citation_markers(content: str) -> list[str]:
    markers: list[str] = []
    for match in _MARKER_PATTERN.finditer(normalize_citation_brackets(content or "")):
        marker = f"[{match.group(1)}]"
        if marker not in markers:
            markers.append(marker)
    return markers


def _fallback_content(draft: ResponseDraft, loaded: list[str]) -> str:
    lines = [f"[{index}] {evidence_id}" for index, evidence_id in enumerate(loaded, 1)]
    return "\n".join(["未能生成有引用支持的回答。以下是本次可引用的资料来源："] + lines)


def validate_citations(
    draft: ResponseDraft,
    *,
    loaded_evidence_ids: list[str],
    visible_evidence_ids: list[str] | None = None,
) -> ResponseOutcome:
    """Keep loaded citations and compact their markers to returned-source order."""
    known = {
        index + 1: evidence_id for index, evidence_id in enumerate(loaded_evidence_ids)
    }
    if visible_evidence_ids is not None:
        visible = set(visible_evidence_ids)
        known = {
            index: identity for index, identity in known.items() if identity in visible
        }
    cleaned = normalize_citation_brackets(draft.content)
    markers = extract_citation_markers(cleaned)

    cited_evidence_ids: list[str] = []
    for marker in markers:
        number = int(marker[1:-1])
        evidence_id = known.get(number)
        if evidence_id is not None and evidence_id not in cited_evidence_ids:
            cited_evidence_ids.append(evidence_id)

    compact_markers = {
        evidence_id: f"[{index}]"
        for index, evidence_id in enumerate(cited_evidence_ids, 1)
    }

    def replace_marker(match: re.Match[str]) -> str:
        evidence_id = known.get(int(match.group(1)))
        return compact_markers.get(evidence_id, "")

    cleaned = _MARKER_PATTERN.sub(replace_marker, cleaned)

    if not cited_evidence_ids:
        return ResponseOutcome(
            response_mode=draft.response_mode,
            content=cleaned,
            citations=[],
            cited_evidence_ids=[],
            partial_reason="no_supported_citations",
        )
    citations = [
        CitationRef(
            evidence_id=evidence_id,
            marker=compact_markers[evidence_id],
        )
        for evidence_id in cited_evidence_ids
    ]
    return ResponseOutcome(
        response_mode=draft.response_mode,
        content=cleaned,
        citations=citations,
        cited_evidence_ids=cited_evidence_ids,
    )
