"""Shared deterministic source selection; no summaries or scoring inputs."""

from __future__ import annotations

import hashlib
import json
import math
import re
from bisect import bisect_left
from collections import Counter
from dataclasses import dataclass, replace

from deeptrace.domain.evidence import Evidence, EvidenceSupport

_TERMS = re.compile(r"[a-zA-Z0-9_]+|[\u3400-\u9fff]+")
_STOP = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "do",
        "does",
        "for",
        "from",
        "how",
        "in",
        "is",
        "it",
        "of",
        "on",
        "or",
        "the",
        "to",
        "what",
        "when",
        "which",
        "with",
    ]
)
_OMITTED = "\n（选段：其余原文已省略，片段边界可能不完整。）"
_IDENTIFIERS = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)*")


@dataclass(frozen=True)
class SourceRange:
    start: int
    end: int
    start_line: int
    end_line: int


@dataclass(frozen=True)
class SourceExcerpt:
    text: str
    ranges: tuple[SourceRange, ...]
    omitted_ranges: tuple[tuple[int, int], ...]
    strategy: str


@dataclass(frozen=True)
class EvidencePassage:
    evidence_id: str
    version: int
    content_hash: str
    passage_id: str
    start: int
    end: int
    start_line: int
    end_line: int
    text: str


def make_evidence_passage(
    record: Evidence, body: str, start: int, end: int
) -> EvidencePassage:
    """Stable label for one nonempty, verbatim Python-character range."""
    if (
        type(start) is not int
        or type(end) is not int
        or not 0 <= start < end <= len(body)
    ):
        raise ValueError("invalid_passage_range")
    identity = _passage_identity(
        record.id, record.version, record.content_hash, start, end
    )
    return EvidencePassage(
        record.id,
        record.version,
        record.content_hash,
        identity,
        start,
        end,
        body.count("\n", 0, start) + 1,
        body.count("\n", 0, end - 1) + 1,
        body[start:end],
    )


def _passage_identity(evidence_id, version, content_hash, start, end):
    key = json.dumps(
        [evidence_id, version, content_hash, start, end],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return "p-" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]


def slice_evidence_passage(
    passage: EvidencePassage, start: int, end: int
) -> EvidencePassage:
    """Slice an already materialized range using absolute Python coordinates."""
    if (
        type(start) is not int
        or type(end) is not int
        or not passage.start <= start < end <= passage.end
    ):
        raise ValueError("invalid_passage_range")
    left, right = start - passage.start, end - passage.start
    return replace(
        passage,
        start=start,
        end=end,
        text=passage.text[left:right],
        passage_id=_passage_identity(
            passage.evidence_id, passage.version, passage.content_hash, start, end
        ),
        start_line=passage.start_line + passage.text.count("\n", 0, left),
        end_line=passage.start_line + passage.text.count("\n", 0, right - 1),
    )


def select_evidence_passages(
    record: Evidence,
    body: str,
    *,
    query: str | None,
    start: int | None,
    limit: int,
    focus_queries: list[str] | None = None,
) -> tuple[EvidencePassage, ...]:
    if type(limit) is not int or limit < 1:
        raise ValueError("passage limit must be a positive integer")
    if start is not None and (type(start) is not int or start < 0):
        raise ValueError("start must be a non-negative integer")
    if query is not None and start is not None:
        raise ValueError("query_and_start_are_exclusive")
    if start is not None:
        first, end = min(start, len(body)), min(start + limit, len(body))
        ranges = [(first, end)] if first < end else []
    else:
        excerpt = select_source_excerpt(
            body, query or "", limit, focus_queries=focus_queries
        )
        ranges = [(r.start, r.end) for r in excerpt.ranges]
    return tuple(
        make_evidence_passage(record, body, first, end) for first, end in ranges
    )


def support_matches_record(
    support: EvidenceSupport, record: Evidence, body: str
) -> bool:
    """Check host coordinates too: model_copy and historical DTOs bypass validation."""
    return (
        support.evidence_id == record.id
        and support.version == record.version
        and support.content_hash == record.content_hash
        and type(support.start) is int
        and type(support.end) is int
        and 0 <= support.start < support.end <= len(body)
        and 1 <= len(support.quote) <= 500
        and support.end - support.start == len(support.quote)
        and body[support.start : support.end] == support.quote
    )


def supported_ranges(
    record: Evidence, body: str, supports: list[EvidenceSupport], limit: int
) -> list[tuple[int, int]]:
    """Reserve whole valid cores globally before spending on optional context."""
    if type(limit) is not int or limit < 1:
        raise ValueError("passage limit must be a positive integer")
    coordinates = list(
        dict.fromkeys(
            (support.start, support.end)
            for support in supports
            if support_matches_record(support, record, body)
        )
    )
    cores = _merge(coordinates)
    if _range_chars(cores) > limit:
        cores = []
        for span in coordinates:
            proposed = _merge([*cores, span])
            if _range_chars(proposed) <= limit:
                cores = proposed

    # Freeze necessary ranges: earlier context must never displace later cores.
    ranges = list(cores)
    for start, end in cores:
        low, high = 0, 120
        while low < high:
            margin = (low + high + 1) // 2
            proposed = _merge(
                [
                    *ranges,
                    (max(0, start - margin), min(len(body), end + margin)),
                ]
            )
            if _range_chars(proposed) <= limit:
                low = margin
            else:
                high = margin - 1
        ranges = _merge(
            [
                *ranges,
                (max(0, start - low), min(len(body), end + low)),
            ]
        )
    return ranges


def _range_chars(ranges: list[tuple[int, int]]) -> int:
    """Length of an already merged raw-text union (not rendered/token cost)."""
    return sum(end - start for start, end in ranges)


def select_supported_passages(
    record: Evidence,
    body: str,
    supports: list[EvidenceSupport],
    *,
    question: str,
    limit: int,
    focus_queries: list[str] | None = None,
) -> tuple[EvidencePassage, ...]:
    """Keep accepted quotes whole before spending the remaining query budget."""
    if type(limit) is not int or limit < 1:
        raise ValueError("passage limit must be a positive integer")
    ranges = supported_ranges(record, body, supports, limit)
    remaining = limit - sum(end - first for first, end in ranges)
    if remaining:
        for passage in select_evidence_passages(
            record,
            body,
            query=question,
            start=None,
            limit=remaining,
            focus_queries=focus_queries,
        ):
            pieces = [(passage.start, passage.end)]
            for first, end in ranges:
                pieces = [
                    (a, b)
                    for left, right in pieces
                    for a, b in ((left, min(right, first)), (max(left, end), right))
                    if a < b
                ]
            ranges = _merge([*ranges, *pieces])
    return tuple(
        make_evidence_passage(record, body, first, end) for first, end in ranges
    )


def _terms(question: str) -> set[str]:
    terms: set[str] = set()
    for match in _TERMS.finditer(question[:4096].casefold()):
        word = match.group()
        if "\u3400" <= word[0] <= "\u9fff":
            terms.update(word[i : i + 2] for i in range(len(word) - 1))
        elif word not in _STOP:
            terms.add(word)
    return terms


def _query_entities(question: str) -> list[str]:
    """Only query-supplied code names, never inferred answer terminology."""
    quoted = set(re.findall(r"`([a-zA-Z_][a-zA-Z0-9_]*)`", question))
    entities = []
    for match in _IDENTIFIERS.finditer(question[:4096]):
        word = match.group()
        if (
            "." in word
            or "_" in word
            or re.search(r"[a-z][A-Z]", word)
            or word in quoted
        ):
            terminal = word.rsplit(".", 1)[-1].casefold()
            if terminal not in entities:
                entities.append(terminal)
    return entities


def _matches(text: str, term: str) -> bool:
    if term.isascii():
        return (
            re.search(r"(?<![a-z0-9_])" + re.escape(term) + r"(?![a-z0-9_])", text)
            is not None
        )
    return term in text


def _section_heading(text: str) -> bool:
    """Markdown headings or extracted qualified API signatures, not mentions."""
    return _heading_text(text) is not None


def _heading_text(text: str) -> str | None:
    first = next(
        (line.strip() for line in text.splitlines() if line.strip() not in {"", "-"}),
        "",
    )
    # Flattened example comments can start with '#'; a long prose/code row is
    # not a reliable standalone section title.
    if len(first) <= 160 and re.match(r"#{1,6}\s", first):
        return first
    if first.endswith(("¶", ")")) and re.match(
        r"(?:\*?(?:class|awaitable|coroutine)\*?\s+)?"
        r"[a-zA-Z_]\w*\.[a-zA-Z_]\w*(?:\.[a-zA-Z_]\w*)*\s*(?:[(*]|¶)",
        first,
    ):
        return first
    return None


def _paragraph_ends(body: str) -> list[int]:
    """Do not turn blank code rows or hash comments into prose boundaries."""
    fences, opened = [], None
    for match in re.finditer(r"(?m)^[ \t]*(`{3,}|~{3,})[^\n]*", body):
        marker = match.group(1)
        if opened is None:
            opened = match.start(), marker
        elif marker[0] == opened[1][0] and len(marker) >= len(opened[1]):
            fences.append((opened[0], match.end()))
            opened = None
    if opened is not None:
        fences.append((opened[0], len(body)))
    return [
        match.end()
        for match in re.finditer(r"\n[ \t\r]*\n", body)
        if not any(a <= match.start() < b for a, b in fences)
    ] + [len(body)]


def _merge(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    merged: list[tuple[int, int]] = []
    for start, end in sorted(ranges):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged


def _render(
    body: str, ranges: list[tuple[int, int]], newlines: list[int]
) -> SourceExcerpt:
    spans = tuple(
        SourceRange(
            start,
            end,
            bisect_left(newlines, start) + 1,
            bisect_left(newlines, end - 1) + 1,
        )
        for start, end in ranges
    )
    parts = [
        f"（原文行 {s.start_line}-{s.end_line}；字符 {s.start}:{s.end}）\n"
        f"{body[s.start : s.end]}"
        for s in spans
    ]
    omitted = []
    cursor = 0
    for start, end in ranges:
        if cursor < start:
            omitted.append((cursor, start))
        cursor = end
    if cursor < len(body):
        omitted.append((cursor, len(body)))
    return SourceExcerpt("\n\n".join(parts) + _OMITTED, spans, tuple(omitted), "query")


def _source_blocks(body: str) -> list[tuple[int, int]]:
    """Whole small paragraphs; sentence/line blocks for longer paragraphs.

    Indivisible oversized units remain whole so callers can report omission.
    Boundaries are heuristic; all returned coordinates address raw text.
    """
    blocks = []
    first = 0
    for end in _paragraph_ends(body):
        if first == end:
            continue
        if end - first <= 900 or re.search(
            r"(?m)^[ \t]*(`{3,}|~{3,})", body[first:end]
        ):
            blocks.append((first, end))
        else:
            boundaries = [
                first + m.end()
                for m in re.finditer(
                    r"(?<=\S)[.!?](?:[ \t]+|\n+)|[。！？][ \t]*", body[first:end]
                )
            ] + [end]
            if len(boundaries) == 1:
                # A sentence-free code/list block uses whole rows. Inline
                # HTML text with a terminating sentence keeps its line group.
                boundaries = [
                    first + m.end() for m in re.finditer(r"\n", body[first:end])
                ] + [end]
            unit_start = block_start = first
            block_end = first
            for unit_end in boundaries:
                if unit_end <= unit_start:
                    continue
                if unit_end - unit_start > 900:
                    if block_start < block_end:
                        blocks.append((block_start, block_end))
                    blocks.append((unit_start, unit_end))
                    block_start = block_end = unit_end
                else:
                    if unit_end - block_start > 900:
                        blocks.append((block_start, block_end))
                        block_start = unit_start
                    block_end = unit_end
                unit_start = unit_end
            if block_start < block_end:
                blocks.append((block_start, block_end))
        first = end
    return blocks


def select_source_excerpt(
    body: str,
    question: str,
    limit: int,
    *,
    focus_queries: list[str] | None = None,
    eligible_ranges: list[tuple[int, int]] | None = None,
) -> SourceExcerpt:
    """Fit verbatim structural blocks, first balancing separately supplied facts.

    Rare terms rank blocks; original position breaks ties. Labels/omissions count
    against the unchanged limit. Matching is not semantic coverage verification.
    """
    if type(limit) is not int or limit < 1:
        raise ValueError("excerpt limit must be a positive integer")
    if not body:
        return SourceExcerpt("", (), (), "full")
    allowed = None
    if eligible_ranges is not None:
        if any(
            type(a) is not int or type(b) is not int or not 0 <= a < b <= len(body)
            for a, b in eligible_ranges
        ):
            raise ValueError("invalid_eligible_range")
        allowed = _merge(eligible_ranges)
        if not allowed:
            return SourceExcerpt("", (), ((0, len(body)),), "no_match")
        # Evaluator callers budget raw ranges, then account for serialized JSON.
        # Retain small actual reads even when their literal query has no match.
        if sum(b - a for a, b in allowed) <= limit:
            return _render(body, allowed, [m.start() for m in re.finditer("\n", body)])
    # Small sources need no lossy retrieval at all. 'full' means verbatim
    # visibility, not that a keyword matched or an answer requirement is met.
    if allowed is None and len(body) <= limit:
        span = SourceRange(0, len(body), 1, body.count("\n", 0, len(body) - 1) + 1)
        return SourceExcerpt(body, (span,), (), "full")
    queries = [*(focus_queries or [])[:6], question]
    if allowed is None and not any(query.strip() for query in queries):
        end = min(len(body), limit)
        span = SourceRange(0, end, 1, body.count("\n", 0, end - 1) + 1)
        return SourceExcerpt(
            body[:end],
            (span,),
            ((end, len(body)),) if end < len(body) else (),
            "prefix" if end < len(body) else "full",
        )
    terms = set().union(*(_terms(query) for query in queries))
    if not any(
        _matches(body[a:b].casefold(), term)
        for a, b in (allowed if allowed is not None else [(0, len(body))])
        for term in terms
    ):
        return SourceExcerpt("", (), ((0, len(body)),), "no_match")
    question_terms = _terms(question)
    focus_terms = [_terms(query) for query in (focus_queries or [])[:6]]
    entities = list(dict.fromkeys(e for q in queries for e in _query_entities(q)))
    newlines = [m.start() for m in re.finditer("\n", body)]
    candidates: list[tuple[int, int, set[str]]] = []
    blocks = (
        [
            (a + left, a + right)
            for a, b in allowed
            for left, right in _source_blocks(body[a:b])
        ]
        if allowed is not None
        else _source_blocks(body)
    )
    section_entities = set()
    section_first = None
    block_entities = {}
    section_heads = {}
    previous_end = None
    for start, end in blocks:
        if previous_end is not None and start != previous_end:
            section_entities, section_first = set(), None
        previous_end = end
        text = body[start:end].casefold()
        direct = {e for e in entities if _matches(text, e)}
        heading = _heading_text(body[start:end])
        if heading is not None:
            section_entities = {e for e in entities if _matches(heading.casefold(), e)}
            section_first = start if section_entities else None
        relevant = direct | section_entities
        block_entities[start] = relevant
        section_heads[start] = section_first
        matched = {term for term in terms if _matches(text, term)}
        matched |= relevant
        if matched:
            candidates.append((start, end, matched))
    frequency = Counter(term for _, _, matched in candidates for term in matched)
    weights = {
        term: 1 + math.log((len(candidates) + 1) / count)
        for term, count in frequency.items()
    }
    average_length = (
        sum(b - a for a, b, _ in candidates) / len(candidates) if candidates else 1
    )
    selected: list[tuple[int, int]] = []

    def score(row, group):
        # Length normalization prevents a large generic paragraph winning merely
        # because it contains more of the same topic words.
        return sum(weights[t] for t in sorted(row[2] & group)) / (
            0.25 + 0.75 * (row[1] - row[0]) / average_length
        )

    def try_add(start: int, end: int) -> bool:
        nonlocal selected
        proposed = _merge([*selected, (start, end)])
        size = (
            sum(b - a for a, b in proposed)
            if allowed is not None
            else len(_render(body, proposed, newlines).text)
        )
        if len(proposed) <= 16 and size <= limit:
            selected = proposed
            return True
        return False

    def ranked_for(group, entity=None):
        return sorted(
            (
                row
                for row in candidates
                if (entity in block_entities[row[0]] if entity else row[2] & group)
            ),
            key=lambda row: (
                -(section_heads[row[0]] is not None),
                -score(row, group),
                row[0],
            ),
        )

    def add_with_heading(row):
        start, end, _ = row
        heading = section_heads[start]
        if heading is not None:
            heading_end = next(b for a, b in blocks if a == heading)
            previous = list(selected)
            if try_add(heading, heading_end) and try_add(start, end):
                return True
            selected[:] = previous
            return False
        return try_add(start, end)

    # Reserve one complete group per target before generic words can consume it.
    for entity in entities:
        for row in ranked_for(terms, entity):
            if add_with_heading(row):
                break
    for group in focus_terms:
        for row in ranked_for(group):
            if add_with_heading(row):
                break
    # With target matches, spend remaining space inside their sections first.
    has_entity_matches = any(block_entities.values())
    ranked = sorted(
        candidates,
        key=lambda row: (
            -(section_heads[row[0]] is not None),
            -bool(block_entities[row[0]]),
            -score(row, question_terms),
            row[0],
        ),
    )
    for row in ranked:
        if has_entity_matches and not block_entities[row[0]]:
            continue
        add_with_heading(row)
    # Whole adjacent conditions in the same identified section, never a next API.
    primary_ranges = list(selected)
    for index, (start, end) in enumerate(blocks):
        if not any(a <= start and end <= b for a, b in primary_ranges):
            continue
        if not block_entities[start] and section_heads[start] is None:
            continue
        if index + 1 < len(blocks):
            first, last = blocks[index + 1]
            if (
                first == end
                and not _section_heading(body[first:last])
                and section_heads[first] == section_heads[start]
            ):
                try_add(first, last)
    if selected:
        return _render(body, selected, newlines)
    return SourceExcerpt("", (), ((0, len(body)),), "budget_omitted")
