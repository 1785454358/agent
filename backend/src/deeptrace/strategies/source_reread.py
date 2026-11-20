"""Bounded source outlines and host-resolved rereads, never semantic evidence."""

import hashlib
import re
from itertools import zip_longest

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from deeptrace.domain.evidence import Evidence
from deeptrace.domain.evidence_anchor import ReadEvidenceAnchor
from deeptrace.harness.context import HarnessContext
from deeptrace.tools.evidence_views import _matches, _source_blocks, _terms
from deeptrace.tools.source_sections import section_at


class SourceReadChoice(BaseModel):
    model_config = ConfigDict(extra="forbid")
    block_id: str = Field(min_length=1, max_length=100)
    target_requirement_ids: list[str] = Field(min_length=1, max_length=6)


class SourceReadAction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    anchor: ReadEvidenceAnchor
    target_requirement_ids: list[str] = Field(default_factory=list, max_length=6)


async def build_source_outline(
    context: HarnessContext,
    records: list[Evidence],
    eligibility: dict[str, str],
    *,
    focus_queries: list[str] | None = None,
    max_entries: int = 128,
) -> tuple[list[dict], dict[str, SourceReadAction], list[str]]:
    if not 1 <= max_entries <= 128:
        raise ValueError("invalid_outline_capacity")
    terms = _terms(" ".join(focus_queries or []))
    candidates, diagnostics = [], []
    admitted = [r for r in records if eligibility.get(r.id) != "ineligible"]
    if len(admitted) > 32:
        diagnostics.append("reread_outline_sources_omitted")
    for record in admitted[:32]:
        try:
            body = await context.evidence_store.read_body(
                context.workspace_id, record.id
            )
        except Exception:  # noqa: BLE001 - isolate a source, not cancellation
            diagnostics.append(f"reread_outline_unavailable:{record.id}")
            continue
        ranges = []
        for start, end in _source_blocks(body):
            if end - start > 900:
                diagnostics.append(f"reread_outline_oversized:{record.id}:{start}")
                # Navigation to a partial window is better than making a long
                # unit invisible. It does not establish condition completeness.
                ranges.extend((a, min(a + 900, end)) for a in range(start, end, 900))
            elif body[start:end].strip():
                ranges.append((start, end))
        if len(ranges) > 32:
            diagnostics.append(f"reread_outline_blocks_omitted:{record.id}")
            # Sample the whole page rather than hiding every later section.
            if terms:
                ranges.sort(key=lambda pair: -sum(
                    _matches(body[pair[0]:pair[1]].casefold(), term) for term in terms
                ))
                ranges = ranges[:32]
            else:
                ranges = [ranges[i * (len(ranges) - 1) // 31] for i in range(32)]
        elif terms:
            ranges.sort(key=lambda pair: -sum(
                _matches(body[pair[0]:pair[1]].casefold(), term) for term in terms
            ))
        local = []
        for start, end in ranges:
            owner = section_at(body, start)
            if owner is not None and end - owner.start <= 900:
                start = owner.start
            anchor = ReadEvidenceAnchor(
                evidence_id=record.id,
                version=record.version,
                content_hash=record.content_hash,
                start=start,
                end=end,
            )
            key = (
                "b-" + hashlib.sha256(repr(anchor.range_key).encode()).hexdigest()[:20]
            )
            text = body[start:end].strip()
            preview = text if len(text) <= 200 else text[:150] + " … " + text[-47:]
            local.append(
                (
                    {
                        "block_id": key,
                        "evidence_id": record.id,
                        "start": start,
                        "end": end,
                        "preview": preview,
                        "heading_only": bool(owner and not body[max(start, owner.heading_end):end].strip()),
                        **({"section_title": owner.title, "section_path": list(owner.path)}
                           if owner is not None else {}),
                    },
                    SourceReadAction(anchor=anchor),
                )
            )
        candidates.append(local)
    ordered = [entry for rank in zip_longest(*candidates) for entry in rank if entry]
    if len(ordered) > max_entries:
        diagnostics.append("reread_outline_capacity_omitted")
    entries = ordered[:max_entries]
    return (
        [e for e, _ in entries],
        {e["block_id"]: a for e, a in entries},
        list(dict.fromkeys(diagnostics)),
    )


def select_local_recovery_reads(entries, blocks, requirements, gap_ids, read_anchors):
    """Only explicit section identifiers authorize automatic navigation.

    The selected range is still read and evaluated normally. No host keyword
    match claims coverage, no stale/subset read counts as new acquisition.
    """
    actions, seen = [], set()
    for requirement in requirements:
        if requirement.id not in gap_ids:
            continue
        query = requirement.description.casefold()
        identifiers = set(re.findall(r"\b\d{3}\b|\b\d+(?:\.\d+)+\b|\b[a-z_]\w*\.[a-z_]\w*(?:\.[a-z_]\w*)*", query))
        if not identifiers:
            continue
        for entry in entries:
            if entry.get("heading_only"):
                continue
            title = entry.get("section_title", "").casefold()
            if not any(_matches(title, identifier) or (
                identifier[0].isalpha() and _matches(title, identifier.rsplit(".", 1)[-1]))
                       for identifier in identifiers):
                continue
            action = blocks[entry["block_id"]]
            a = action.anchor
            ranges = sorted((old.start, old.end) for old in read_anchors
                if old.evidence_id == a.evidence_id and old.version == a.version and old.content_hash == a.content_hash)
            cursor = a.start
            for first, end in ranges:
                if first <= cursor:
                    cursor = max(cursor, end)
            if cursor >= a.end or a.range_key in seen:
                continue
            actions.append(action.model_copy(update={"target_requirement_ids": [requirement.id]}))
            seen.add(a.range_key)
            break
        if len(actions) == 2:
            break
    return actions


def resolve_source_reads(
    payload: dict | None,
    blocks: dict[str, SourceReadAction],
    *,
    gap_ids: set[str],
    requirement_ids: set[str],
) -> list[SourceReadAction]:
    if not gap_ids <= requirement_ids:
        raise ValueError("invalid_gap_ids")
    candidates = (payload or {}).get("reads")
    if not isinstance(candidates, list):
        return []
    actions, seen = [], set()
    for candidate in candidates[:24]:
        try:
            choice = SourceReadChoice.model_validate(candidate)
        except ValidationError:
            continue
        targets = choice.target_requirement_ids
        if (
            choice.block_id not in blocks
            or choice.block_id in seen
            or len(set(targets)) != len(targets)
            or not set(targets) <= requirement_ids
        ):
            continue
        remaining = [r for r in targets if r in gap_ids]
        if not remaining:
            continue
        actions.append(
            blocks[choice.block_id].model_copy(
                update={"target_requirement_ids": remaining}
            )
        )
        seen.add(choice.block_id)
        if len(actions) == 2:
            break
    return actions
