"""Read-first source ranges and short raw quote units; no semantic claims."""

import re
from collections.abc import Iterator

from pydantic import ValidationError

from deeptrace.domain.evidence import Evidence, EvidenceSupport
from deeptrace.domain.evidence_anchor import ReadEvidenceAnchor
from deeptrace.tools.evidence_views import (
    EvidencePassage,
    _merge,
    make_evidence_passage,
    select_evidence_passages,
    select_source_excerpt,
    slice_evidence_passage,
    supported_ranges,
)


def _subtract(
    start: int, end: int, selected: list[tuple[int, int]]
) -> list[tuple[int, int]]:
    pieces = [(start, end)]
    for first, stop in selected:
        pieces = [
            (a, b)
            for left, right in pieces
            for a, b in ((left, min(right, first)), (max(left, stop), right))
            if a < b
        ]
    return pieces


def _quote_ranges(text: str, limit: int = 500) -> Iterator[tuple[int, int]]:
    """Greedily pack intact sentences/lines, falling back only for long units."""
    boundaries = [
        m.end() for m in re.finditer(r"(?<=[.!?])[ \t]+|(?<=[。！？])[ \t]*|\n", text)
    ] + [len(text)]
    first = 0
    while first < len(text):
        ceiling = min(first + limit, len(text))
        fitting = [end for end in boundaries if first < end <= ceiling]
        end = max(fitting) if fitting else ceiling
        yield first, end
        first = end


def select_read_passages(
    record: Evidence,
    body: str,
    supports: list[EvidenceSupport],
    anchors: list[ReadEvidenceAnchor],
    *,
    question: str,
    focus_queries: list[str],
    limit: int,
    candidate_supports: list[EvidenceSupport] | None = None,
) -> tuple[tuple[EvidencePassage, ...], list[str]]:
    if type(limit) is not int or limit < 1:
        raise ValueError("passage limit must be a positive integer")
    selected = supported_ranges(record, body, supports, limit)
    diagnostics = []
    for a, b in supported_ranges(record, body, candidate_supports or [], limit):
        for start, end in _subtract(a, b, selected):
            remaining = limit - sum(stop - first for first, stop in selected)
            if end - start <= remaining:
                selected = _merge([*selected, (start, end)])
            else:
                diagnostics.append("research_finding_material_omitted")
    valid_ranges = []
    for candidate in anchors:
        try:
            anchor = ReadEvidenceAnchor.model_validate(candidate.model_dump())
        except (ValidationError, AttributeError):
            diagnostics.append("invalid_read_anchor")
            continue
        if (
            anchor.evidence_id != record.id
            or anchor.version != record.version
            or anchor.content_hash != record.content_hash
            or anchor.end > len(body)
        ):
            diagnostics.append("invalid_read_anchor")
            continue
        valid_ranges.append((anchor.start, anchor.end))

    remaining = limit - sum(b - a for a, b in selected)
    if remaining and valid_ranges:
        available = [
            piece
            for a, b in _merge(valid_ranges)
            for piece in _subtract(a, b, selected)
        ]
        excerpt = select_source_excerpt(
            body,
            question,
            remaining,
            focus_queries=focus_queries,
            eligible_ranges=available,
        )
        selected = _merge([*selected, *((s.start, s.end) for s in excerpt.ranges)])
    if any(_subtract(a, b, selected) for a, b in valid_ranges):
        diagnostics.append("read_anchor_omitted")
    if remaining and not valid_ranges:
        for passage in select_evidence_passages(
            record,
            body,
            query=question,
            start=None,
            limit=remaining,
            focus_queries=focus_queries,
        ):
            for start, end in _subtract(passage.start, passage.end, selected):
                room = limit - sum(b - a for a, b in selected)
                if end - start <= room:
                    selected = _merge([*selected, (start, end)])
    return tuple(make_evidence_passage(record, body, a, b) for a, b in selected), list(
        dict.fromkeys(diagnostics)
    )


def split_quote_units(
    passages: tuple[EvidencePassage, ...], supports: list[EvidenceSupport]
) -> tuple[EvidencePassage, ...]:
    units = []
    for passage in passages:
        protected = []
        for support in supports:
            if (
                support.evidence_id == passage.evidence_id
                and support.version == passage.version
                and support.content_hash == passage.content_hash
                and type(support.start) is int
                and type(support.end) is int
                and passage.start <= support.start < support.end <= passage.end
                and 1 <= len(support.quote) <= 500
                and passage.text[
                    support.start - passage.start : support.end - passage.start
                ]
                == support.quote
            ):
                units.append(
                    slice_evidence_passage(passage, support.start, support.end)
                )
                protected.append((support.start, support.end))
        for start, end in _subtract(passage.start, passage.end, protected):
            for left, right in _quote_ranges(
                passage.text[start - passage.start : end - passage.start]
            ):
                units.append(
                    slice_evidence_passage(passage, start + left, start + right)
                )
    return tuple({p.passage_id: p for p in units}.values())
