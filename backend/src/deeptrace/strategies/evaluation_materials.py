"""Bounded evaluator input and its exact, call-local visible reference map."""

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field

from deeptrace.domain import (
    Evidence,
    EvidenceLifecycleStatus,
    Finding,
    ResearchRequirement,
)
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
from deeptrace.strategies.publication_dates import (
    source_is_news,
    visible_publication_dates,
)
from deeptrace.tools.evidence_units import select_read_passages, split_quote_units
from deeptrace.tools.evidence_views import EvidencePassage, _merge
from deeptrace.tools.source_sections import section_at
from deeptrace.research.observations import visible_research_records


@dataclass(frozen=True)
class ReferenceEvaluationView:
    prompt: str
    passages: tuple[EvidencePassage, ...]
    references: dict[str, EvidencePassage]
    unread_ids: tuple[str, ...]
    diagnostics: tuple[str, ...]
    allocation: BudgetAllocation
    source_ids: dict[str, str]
    news_source_ids: frozenset[str] = frozenset()
    support_groups: dict[str, tuple[str, ...]] = field(default_factory=dict)
    evidence_records: tuple[Evidence, ...] = ()
    bodies: dict[str, str] = field(default_factory=dict)


async def assemble_reference_evaluation_view(
    context: HarnessContext,
    *,
    question: str,
    requirements: list[ResearchRequirement],
    evidence_ids: list[str],
    findings: list[Finding],
    read_anchors: list[ReadEvidenceAnchor],
    preferred_read_anchors: list[ReadEvidenceAnchor] | None = None,
    research_findings: list[Finding] | None = None,
    prefer_research_passages: bool = False,
    budget: TokenBudgetConfig | None = None,
    pinned: str = "",
    previous_read_ranges: list[dict] | None = None,
    measure_prompt: Callable[[str], int] | None = None,
    prior_verified_requirements: list[dict] | None = None,
) -> ReferenceEvaluationView:
    config = budget or TokenBudgetConfig()
    ids = list(dict.fromkeys(evidence_ids))
    groups, unread, diagnostics, sources = [], [], [], []
    evidence_records: list[Evidence] = []
    bodies: dict[str, str] = {}
    news_source_ids = set()
    supports = [s for f in findings for s in f.supports]
    # Keep enough whole reads for independent requirements. The global token
    # and citation caps still govern the final serialized view.
    reading_limit = 3000 if prefer_research_passages else min(6000, max(3000, len(requirements) * 1000))
    for index, identity in enumerate(ids):
        # Independent branches can legitimately acquire more than eight
        # sources. Admit their metadata and compete for whole reading groups
        # under the global token/quote budget instead of hiding later tracks.
        if index >= 32:
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
            evidence_records.append(record)
            bodies[identity] = body
            if source_is_news(body):
                news_source_ids.add(identity)
        except Exception:  # noqa: BLE001 - isolate a source, not cancellation
            unread.append(identity)
            continue
        local_supports = [s for s in supports if s.evidence_id == identity]
        local_anchors = [a for a in read_anchors if a.evidence_id == identity]
        local_preferred = [a for a in preferred_read_anchors or [] if a.evidence_id == identity]
        source_limit = reading_limit
        if prefer_research_passages:
            # A new fixed 3000-character crop must not undo requirement-driven
            # acquisition. Retain actual valid reads, capped per source and by
            # the existing global whole-group token allocator below.
            read_ranges = _merge([(a.start, a.end) for a in local_anchors
                if a.version == record.version and a.content_hash == record.content_hash
                and 0 <= a.start < a.end <= len(body)])
            source_limit = min(9000, max(reading_limit, sum(b-a for a, b in read_ranges)))
        passages, issues = select_read_passages(
            record,
            body,
            local_supports,
            local_anchors,
            question=question,
            focus_queries=[r.description for r in requirements],
            limit=source_limit,
            preferred_anchors=local_preferred,
            candidate_supports=([s for f in research_findings or [] for s in f.supports if s.evidence_id == identity]
                                if prefer_research_passages else []),
        )
        if local_supports and previous_read_ranges and not local_preferred:
            previous = _merge([(row["start"], row["end"]) for row in previous_read_ranges
                if row["evidence_id"] == identity and row["version"] == record.version
                and row["content_hash"] == record.content_hash])
            # Drop only whole previously assessed reading groups without a
            # retained proof. Never shorten the context of a supported claim,
            # remove new text, or skip an explicit recovery read.
            retained = tuple(p for p in passages if not (
                any(a <= p.start and p.end <= b for a, b in previous)
                and not any(s.start < p.end and p.start < s.end for s in local_supports)))
            if retained and len(retained) < len(passages):
                passages = retained
                issues.append("previously_evaluated_groups_omitted")
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
                "published_at": record.published_at.isoformat() if record.published_at else None,
                "publication_date_scope": "report_date" if identity in news_source_ids else "page_date_requires_verification",
                "requested_url": record.metadata.get("requested_url"),
                "final_url": record.metadata.get("final_url"),
                "publisher_canonical_url": record.metadata.get(
                    "publisher_canonical_url"
                ),
            }
        )

    def priority(unit: EvidencePassage) -> int:
        if any(
            a.evidence_id == unit.evidence_id and a.version == unit.version
            and a.content_hash == unit.content_hash and a.start <= unit.start
            and unit.end <= a.end and any(a.range_key == old.range_key for old in read_anchors)
            for a in preferred_read_anchors or []
        ):
            return -1
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
    ) -> tuple[str, dict[str, EvidencePassage], dict[str, tuple[str, ...]]]:
        refs = {
            f"p{i}": p
            for i, p in enumerate((p for _, group in visible for p in group), 1)
        }
        support_groups = {
            f"g{index}": tuple(ref for ref, p in refs.items() if p in group)
            for index, (_, group) in enumerate(visible, 1)
        }
        payload = {
            "question": question,
            "requirements": requirement_data,
            "sources": sources,
            "research_findings": visible_research_records(
                [*findings, *(research_findings or [])],
                {ref: [passage] for ref, passage in refs.items()},
            ),
            "reading_groups": [
                [ref for ref, p in refs.items() if p in group] for _, group in visible
            ],
            "section_navigation": [
                {"group": f"g{index}", "path": list(owner.path),
                 "heading_range": [owner.start, owner.heading_end],
                 "usage": "navigation_only_not_a_support_reference"}
                for index, (_, group) in enumerate(visible, 1)
                if (owner := section_at(bodies[group[0].evidence_id], group[0].start)) is not None
            ],
            "support_groups": [
                {"ref": ref, "source": f"s{ids.index(refs[members[0]].evidence_id) + 1}",
                 "passages": list(members)}
                for ref, members in support_groups.items()
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
        if prior_verified_requirements:
            payload["prior_verified_requirements"] = prior_verified_requirements
        if prefer_research_passages:
            dated_refs = {}
            for ref, passage in refs.items():
                source = f"s{ids.index(passage.evidence_id) + 1}"
                for published_on in visible_publication_dates(passage.text, source_is_news_page=passage.evidence_id in news_source_ids):
                    key = (source, published_on.isoformat())
                    dated_refs.setdefault(key, []).append({"ref": ref})
            payload["publication_dates"] = [
                {"source": source, "published_on": day, "date_refs": references[:2]}
                for (source, day), references in sorted(dated_refs.items())
            ]
        return "\nEVIDENCE_VIEW_JSON:\n" + json.dumps(
            payload, ensure_ascii=False, separators=(",", ":")
        ), refs, support_groups

    empty_prompt, _, _ = render([])
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
    prompt, refs, support_groups = render(visible)
    # Recheck the actual serialized payload: allocator segments may tokenize
    # differently from joined JSON. Never expose a ref dropped in this pass.
    measure = measure_prompt or (lambda text: count_tokens(pinned + text))
    while visible and measure(prompt) > config.input_budget:
        removed = visible.pop()
        allocation.included.pop(removed[0], None)
        allocation.dropped.append(removed[0])
        prompt, refs, support_groups = render(visible)
    allocation.used_tokens = measure(prompt)
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
        prompt=prompt,
        passages=tuple(visible_passages),
        references=refs,
        unread_ids=tuple(dict.fromkeys(unread)),
        diagnostics=tuple(dict.fromkeys(diagnostics)),
        allocation=allocation,
        source_ids={s["source"]: ids[int(s["source"][1:]) - 1] for s in sources},
        news_source_ids=frozenset(news_source_ids),
        support_groups=support_groups,
        evidence_records=tuple(evidence_records),
        bodies=bodies,
    )
