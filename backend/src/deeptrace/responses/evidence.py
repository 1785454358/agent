"""Local writer materials; bodies never enter response graph state."""

from dataclasses import dataclass
import hashlib
import json
from typing import Any

from deeptrace.domain import Evidence, EvidenceSupport, Finding, ResponseInput
from deeptrace.harness.context import HarnessContext
from deeptrace.strategies.evidence_evaluation import coverage_complete
from deeptrace.research.observations import observation_supports, visible_research_records
from deeptrace.tools.evidence_views import (
    EvidencePassage,
    select_source_excerpt,
    select_supported_passages,
    support_matches_record,
    make_evidence_passage,
    _merge,
)


@dataclass(frozen=True)
class ResponseMaterials:
    sources: list[str]
    selections: list[dict[str, Any]]
    passages_by_source: dict[str, tuple[EvidencePassage, ...]]
    findings: list[Finding]
    grounded: bool
    issue: str | None


def _source_block(evidence: Evidence, excerpt: str, marker: str, records=None) -> str:
    return (
        f"{marker} id={evidence.id}\n"
        f"标题：{evidence.title}\n来源：{evidence.canonical_url}\n正文摘录：\n{excerpt}"
        + ("\n研究记录（由上述原文提取；缺字段仅表示本次未核实，不是原文未披露；仍需核对实验对应关系）：\n"
           + json.dumps(records, ensure_ascii=False) if records else "")
    )


async def assemble_response_materials(
    context: HarnessContext,
    response_input: ResponseInput,
    loaded: list[Evidence],
    per_source_chars: int,
    *,
    include_extra: bool = True,
    max_support_chars: int | None = None,
) -> ResponseMaterials:
    research = response_input.research_outcome
    eligibility = research.source_eligibility if research else None
    if eligibility is not None:
        loaded = [r for r in loaded if eligibility.get(r.id) == "eligible"]
    verified_finding_ids = response_input.verified_finding_ids
    source_findings = list(research.findings if research else [])
    if verified_finding_ids is not None:
        accepted_ids = set(verified_finding_ids)
        source_findings = [
            finding for finding in source_findings if finding.id in accepted_ids
        ]
        # Verification admits claims, not source bodies. Eligible originals
        # still let the writer explain uncertainty or answer omitted points;
        # rejected candidate claims themselves must never enter the prompt.
    grounded = research is not None and research.evidence_contract_version in (2, 3)
    grounding_issue = None
    if grounded and not research.delivery_first and (
        research.termination_reason != "completed"
        or not coverage_complete(research.model_dump())
    ):
        grounding_issue = (
            research.termination_reason
            if research.termination_reason != "completed"
            else "insufficient_evidence"
        )
    tenant = context.workspace_id
    # Each material view reads bodies once; corrective retries reuse that view.
    sources: list[str] = []
    selections: list[dict[str, Any]] = []
    bodies = {}
    passages_by_source = {}
    for index, record in enumerate(loaded, 1):
        try:
            body = await context.evidence_store.read_body(tenant, record.id)
        except PermissionError:
            raise
        except Exception:  # noqa: BLE001 - isolate source IO; cancellation propagates
            body = ""
        bodies[record.id] = body
        supports = (
            [
                s
                for f in source_findings
                for s in f.supports
                if s.evidence_id == record.id
            ]
            if grounded
            else []
        )
        if grounded and research.delivery_first:
            # These are actual tool reads, not another keyword retrieval.
            # Keep them intact here; the common token allocator owns the one
            # writer/reviewer-visible window, rather than a per-source recrop.
            body_matches = record.content_hash == "sha256:" + hashlib.sha256(body.encode("utf-8")).hexdigest()
            ranges = _merge([(a.start, a.end) for a in research.read_anchors
                if a.evidence_id == record.id and a.version == record.version
                and body_matches and a.content_hash == record.content_hash and 0 <= a.start < a.end <= len(body)])
            passages = tuple(make_evidence_passage(record, body, a, b) for a, b in ranges)
            passages_by_source[record.id] = passages
            text = "\n\n".join(f"（原文字符 {p.start}:{p.end}）\n{p.text}" for p in passages)
            ranges = [{"start":p.start,"end":p.end,"start_line":p.start_line,"end_line":p.end_line} for p in passages]
            strategy, omitted = "actual-reads", []
        elif grounded:
            required = [s for f in source_findings for s in observation_supports(f)
                        if s.evidence_id == record.id]
            supports = list(dict.fromkeys(s.model_dump_json() for s in [*required, *supports]))
            supports = [EvidenceSupport.model_validate_json(s) for s in supports]
            passages = select_supported_passages(
                record,
                body,
                supports,
                question=response_input.question,
                limit=per_source_chars,
                focus_queries=[r.description for r in research.requirements],
                # Without accepted supports this is the primary reading window,
                # not optional expansion. The shared token assembler still caps it.
                include_extra=include_extra or not supports,
                max_support_chars=None if required else max_support_chars,
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
        cards = visible_research_records(source_findings, {f"[{index}]": list(passages)}) if grounded else []
        sources.append(_source_block(record, text, f"[{index}]", cards))
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
    candidates = list(source_findings)
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
        if len(candidates) != len(source_findings):
            grounding_issue = grounding_issue or "invalid_finding_support"
    return ResponseMaterials(
        sources, selections, passages_by_source, candidates, grounded, grounding_issue
    )
