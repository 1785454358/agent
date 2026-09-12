"""Deterministic response-mode selection and citation validation policy."""

from __future__ import annotations

import re

from deeptrace.domain import CitationRef, ResponseMode, ResponseOutcome
from deeptrace.responses.models import ResponseDraft


_MAX_RESPONSE_INPUT_CHARS = 500

_REPORT_TAIL_FORMS = ("报告形式", "报告格式", "完整报告", "正式报告")
_BRIEF_WORDS = ("总结", "摘要", "简报", "对比", "归纳", "要点", "brief", "summary", "tldr")
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


def extract_citation_markers(content: str) -> list[str]:
    markers: list[str] = []
    for match in _MARKER_PATTERN.finditer(content or ""):
        marker = f"[{match.group(1)}]"
        if marker not in markers:
            markers.append(marker)
    return markers


def _fallback_content(draft: ResponseDraft, loaded: list[str]) -> str:
    lines = [f"[{index}] {evidence_id}" for index, evidence_id in enumerate(loaded, 1)]
    return "\n".join(["未能生成有引用支持的回答。以下是本次可引用的资料来源："] + lines)


def validate_citations(
    draft: ResponseDraft, *, loaded_evidence_ids: list[str]
) -> ResponseOutcome:
    """Keep only citations whose Evidence was loaded; never invent replacements."""
    known = {index + 1: evidence_id for index, evidence_id in enumerate(loaded_evidence_ids)}
    markers = extract_citation_markers(draft.content)

    citations: list[CitationRef] = []
    cleaned = draft.content
    for marker in markers:
        number = int(marker[1:-1])
        evidence_id = known.get(number)
        if evidence_id is None:
            cleaned = cleaned.replace(marker, "")
            continue
        if all(citation.evidence_id != evidence_id for citation in citations):
            citations.append(CitationRef(evidence_id=evidence_id, marker=marker))

    if not citations:
        return ResponseOutcome(
            response_mode=draft.response_mode,
            content=cleaned,
            citations=[],
            cited_evidence_ids=[],
            partial_reason="no_supported_citations",
        )
    return ResponseOutcome(
        response_mode=draft.response_mode,
        content=cleaned,
        citations=citations,
        cited_evidence_ids=[citation.evidence_id for citation in citations],
    )
