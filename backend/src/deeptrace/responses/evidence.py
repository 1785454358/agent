"""Local writer materials; bodies never enter response graph state."""

from dataclasses import dataclass
from typing import Any

from deeptrace.domain import Evidence, Finding, ResponseInput
from deeptrace.harness.context import HarnessContext
from deeptrace.strategies.evidence_evaluation import coverage_complete
from deeptrace.tools.evidence_views import (
    EvidencePassage,
    select_source_excerpt,
    select_supported_passages,
    support_matches_record,
)


@dataclass(frozen=True)
class ResponseMaterials:
    sources: list[str]
    selections: list[dict[str, Any]]
    passages_by_source: dict[str, tuple[EvidencePassage, ...]]
    findings: list[Finding]
    grounded: bool
    issue: str | None


def _source_block(evidence: Evidence, excerpt: str, marker: str) -> str:
    return (
        f"{marker} id={evidence.id}\n"
        f"标题：{evidence.title}\n来源：{evidence.canonical_url}\n正文摘录：\n{excerpt}"
    )


async def assemble_response_materials(
    context: HarnessContext,
    response_input: ResponseInput,
    loaded: list[Evidence],
    per_source_chars: int,
) -> ResponseMaterials:
    research = response_input.research_outcome
    eligibility = research.source_eligibility if research else None
    if eligibility is not None:
        loaded = [r for r in loaded if eligibility.get(r.id) == "eligible"]
    grounded = research is not None and research.evidence_contract_version in (2, 3)
    grounding_issue = None
    if grounded and (
        research.termination_reason != "completed"
        or not coverage_complete(research.model_dump())
    ):
        grounding_issue = (
            research.termination_reason
            if research.termination_reason != "completed"
            else "insufficient_evidence"
        )
    tenant = context.workspace_id
    # 证据正文只读一次；纠正重试复用同一批材料，避免重复 IO。
    sources: list[str] = []
    selections: list[dict[str, Any]] = []
    bodies = {}
    passages_by_source = {}
    for index, record in enumerate(loaded, 1):
        try:
            body = await context.evidence_store.read_body(tenant, record.id)
        except Exception:  # noqa: BLE001 - isolate source IO; cancellation propagates
            body = ""
        bodies[record.id] = body
        supports = (
            [
                s
                for f in research.findings
                for s in f.supports
                if s.evidence_id == record.id
            ]
            if grounded
            else []
        )
        if grounded:
            passages = select_supported_passages(
                record,
                body,
                supports,
                question=response_input.question,
                limit=per_source_chars,
            )
            passages_by_source[record.id] = passages
            text = "\n\n".join(
                f"（原文字符 {p.start}:{p.end}；passage_id={p.passage_id}）\n{p.text}"
                for p in passages
            )
            ranges = [
                {
                    "start": p.start,
                    "end": p.end,
                    "start_line": p.start_line,
                    "end_line": p.end_line,
                }
                for p in passages
            ]
            strategy, omitted = "support-first-v2", []
        else:
            excerpt = select_source_excerpt(
                body, response_input.question, per_source_chars
            )
            text, ranges, strategy, omitted = (
                excerpt.text,
                [vars(span) for span in excerpt.ranges],
                excerpt.strategy,
                excerpt.omitted_ranges,
            )
        sources.append(_source_block(record, text, f"[{index}]"))
        selections.append(
            {
                "evidence_id": record.id,
                "segment": f"source_{index}",
                "strategy": strategy,
                "body_chars": len(body),
                "excerpt_chars": len(text),
                "pre_token_ranges": ranges,
                "omitted_ranges": omitted,
            }
        )
    candidates = list(research.findings if research else [])
    if eligibility is not None:
        candidates = [
            f
            for f in candidates
            if f.supports
            and all(eligibility.get(s.evidence_id) == "eligible" for s in f.supports)
        ]
    if grounded:
        by_id = {r.id: r for r in loaded}
        candidates = [
            f
            for f in candidates
            if f.supports
            and set(f.evidence_ids) == {s.evidence_id for s in f.supports}
            and all(
                s.evidence_id in by_id
                and support_matches_record(
                    s, by_id[s.evidence_id], bodies[s.evidence_id]
                )
                for s in f.supports
            )
        ]
        if len(candidates) != len(research.findings):
            grounding_issue = grounding_issue or "invalid_finding_support"
    return ResponseMaterials(
        sources, selections, passages_by_source, candidates, grounded, grounding_issue
    )
