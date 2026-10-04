"""Bounded evaluator input and its exact, call-local visible reference map."""

import json
import logging
from dataclasses import dataclass

from deeptrace.domain import EvidenceLifecycleStatus, Finding, ResearchRequirement
from deeptrace.domain.evidence_anchor import ReadEvidenceAnchor
from deeptrace.harness.context import HarnessContext
from deeptrace.harness.token_budget import (
    BudgetAllocation,
    Segment,
    SegmentPriority,
    TokenBudgetConfig,
    assemble_with_budget,
    count_tokens,
)
from deeptrace.tools.evidence_units import select_read_passages, split_quote_units
from deeptrace.tools.evidence_views import EvidencePassage


@dataclass(frozen=True)
class ReferenceEvaluationView:
    prompt: str
    passages: tuple[EvidencePassage, ...]
    references: dict[str, EvidencePassage]
    unread_ids: tuple[str, ...]
    diagnostics: tuple[str, ...]
    allocation: BudgetAllocation
    source_ids: dict[str, str]


async def assemble_reference_evaluation_view(
    context: HarnessContext,
    *,
    question: str,
    requirements: list[ResearchRequirement],
    evidence_ids: list[str],
    findings: list[Finding],
    read_anchors: list[ReadEvidenceAnchor],
    research_findings: list[Finding] | None = None,
    budget: TokenBudgetConfig | None = None,
    pinned: str = "",
) -> ReferenceEvaluationView:
    config = budget or TokenBudgetConfig()
    ids = list(dict.fromkeys(evidence_ids))
    groups, unread, diagnostics, sources = [], [], [], []
    supports = [s for f in findings for s in f.supports]
    for index, identity in enumerate(ids):
        if index >= 8:
            unread.append(identity)
            continue
        try:
            record = await context.evidence_store.get(context.workspace_id, identity)
            if record.status is not EvidenceLifecycleStatus.ACTIVE:
                unread.append(identity)
                continue
            body = await context.evidence_store.read_body(
                context.workspace_id, identity
            )
        except Exception:  # noqa: BLE001 - isolate a source, not cancellation
            unread.append(identity)
            continue
        local_supports = [s for s in supports if s.evidence_id == identity]
        local_anchors = [a for a in read_anchors if a.evidence_id == identity]
        passages, issues = select_read_passages(
            record,
            body,
            local_supports,
            local_anchors,
            question=question,
            focus_queries=[r.description for r in requirements],
            limit=3000,
        )
        diagnostics.extend(f"{issue}:{identity}" for issue in issues)
        if not passages:
            unread.append(identity)
        for passage in passages:
            # A reading range is indivisible; short citations inside it are
            # coordinates, not independent semantic evidence units.
            group = sorted(
                split_quote_units((passage,), local_supports),
                key=lambda p: (p.start, p.end),
            )
            if group:
                groups.append((passage.passage_id, group))
        sources.append(
            {
                "source": f"s{index + 1}",
                "title": record.title,
                "url": record.canonical_url,
                "requested_url": record.metadata.get("requested_url"),
                "final_url": record.metadata.get("final_url"),
                "publisher_canonical_url": record.metadata.get(
                    "publisher_canonical_url"
                ),
            }
        )

    def priority(unit: EvidencePassage) -> int:
        if any(
            s.evidence_id == unit.evidence_id
            and s.version == unit.version
            and s.content_hash == unit.content_hash
            and s.start == unit.start
            and s.end == unit.end
            and s.quote == unit.text
            for s in supports
        ):
            return 0
        if any(
            a.evidence_id == unit.evidence_id
            and a.version == unit.version
            and a.content_hash == unit.content_hash
            and a.start <= unit.start
            and unit.end <= a.end
            for a in read_anchors
        ):
            return 2
        return 3

    # Round-robin source groups within each admission priority. A long early
    # source must not spend every global slot before a later fact is considered.
    source_positions, group_positions = {}, {}
    for key, group in groups:
        identity = group[0].evidence_id
        group_positions[key] = source_positions.get(identity, 0)
        source_positions[identity] = group_positions[key] + 1
    groups.sort(
        key=lambda g: (
            min(priority(p) for p in g[1]),
            group_positions[g[0]],
            ids.index(g[1][0].evidence_id),
        )
    )
    units = [p for _, group in groups for p in group]
    candidates, capacity = [], 0
    for key, group in groups:
        if capacity + len(group) > 128:
            diagnostics.append("quote_unit_capacity")
            unread.append(group[0].evidence_id)
        else:
            candidates.append((key, group))
            capacity += len(group)
    requirement_data = [r.model_dump(mode="json") for r in requirements]

    def render(
        visible: list[tuple[str, list[EvidencePassage]]],
    ) -> tuple[str, dict[str, EvidencePassage]]:
        refs = {
            f"p{i}": p
            for i, p in enumerate((p for _, group in visible for p in group), 1)
        }
        payload = {
            "question": question,
            "requirements": requirement_data,
            "sources": sources,
            "research_findings": [],
            "reading_groups": [
                [ref for ref, p in refs.items() if p in group] for _, group in visible
            ],
            "passages": [
                {
                    "ref": ref,
                    "source": f"s{ids.index(p.evidence_id) + 1}",
                    "text": p.text,
                }
                for ref, p in refs.items()
            ],
        }
        return "\nEVIDENCE_VIEW_JSON:\n" + json.dumps(
            payload, ensure_ascii=False, separators=(",", ":")
        ), refs

    empty_prompt, _ = render([])
    segments = [Segment("pinned", pinned + empty_prompt, SegmentPriority.PINNED)]
    for key, group in candidates:
        text = (
            json.dumps(
                [
                    {
                        "ref": f"p{index}",
                        "source": f"s{ids.index(p.evidence_id) + 1}",
                        "text": p.text,
                    }
                    for index, p in enumerate(group, 1)
                ],
                ensure_ascii=False,
                separators=(",", ":"),
            )
            + ",\n"
        )
        segments.append(Segment(key, text, SegmentPriority.HIGH, min_tokens=0))
    _, allocation = assemble_with_budget(segments, config)
    visible = [g for g in candidates if g[0] in allocation.included]
    prompt, refs = render(visible)
    # Recheck the actual serialized payload: allocator segments may tokenize
    # differently from joined JSON. Never expose a ref dropped in this pass.
    while visible and count_tokens(pinned + prompt) > config.input_budget:
        removed = visible.pop()
        allocation.included.pop(removed[0], None)
        allocation.dropped.append(removed[0])
        prompt, refs = render(visible)
    allocation.used_tokens = count_tokens(pinned + prompt)
    allocation.pinned_overflow = allocation.used_tokens > config.input_budget
    allocation.bound = bool(allocation.dropped or allocation.pinned_overflow)
    visible_passages = list(refs.values())
    visible_ids = {p.passage_id for p in visible_passages}
    unread.extend(p.evidence_id for p in units if p.passage_id not in visible_ids)
    if allocation.dropped:
        diagnostics.append("evaluation_material_omitted")
    for unit in units:
        try:
            await context.event_sink.emit(
                "evidence.view",
                {
                    "stage": "evaluation",
                    "evidence_id": unit.evidence_id,
                    "version": unit.version,
                    "content_hash": unit.content_hash,
                    "start": unit.start,
                    "end": unit.end,
                    "passage_id": unit.passage_id,
                    "visibility": unit.passage_id in visible_ids,
                },
            )
        except Exception:
            logging.getLogger(__name__).warning(
                "Evidence-view telemetry unavailable", exc_info=True
            )
    return ReferenceEvaluationView(
        prompt,
        tuple(visible_passages),
        refs,
        tuple(dict.fromkeys(unread)),
        tuple(dict.fromkeys(diagnostics)),
        allocation,
        {s["source"]: ids[int(s["source"][1:]) - 1] for s in sources},
    )
