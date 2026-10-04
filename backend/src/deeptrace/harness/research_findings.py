"""Branch-local actual-read references and raw-supported candidate findings."""

import hashlib
import json
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

from deeptrace.domain.evidence import EvidenceLifecycleStatus, EvidenceSupport, Finding
from deeptrace.domain.evidence_anchor import ReadEvidenceAnchor
from deeptrace.harness.read_anchors import capture_read_anchors
from deeptrace.tools.evidence_units import split_quote_units
from deeptrace.tools.evidence_views import EvidencePassage

MAX_READ_REFERENCES = 128
MAX_RESEARCH_FINDINGS = 20


class RecordFindingDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    claim: str = Field(min_length=1, max_length=1000)
    refs: list[str] = Field(min_length=1, max_length=3)
    confidence: float = Field(ge=0, le=1)

    @field_validator("refs")
    @classmethod
    def distinct_refs(cls, values):
        if len(values) != len(set(values)) or any(
            re.fullmatch(r"n[1-9][0-9]{0,2}", v) is None for v in values
        ):
            raise ValueError("invalid_read_reference")
        return values

    @field_validator("claim")
    @classmethod
    def nonblank_claim(cls, value):
        if not value.strip():
            raise ValueError("empty_research_claim")
        return value


class RecordFindingsArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")
    findings: list[RecordFindingDraft] = Field(min_length=1, max_length=5)


def number_read_preview(preview, references):
    original = dict(references)
    try:
        payload = json.loads(preview)
        _, diagnostics = capture_read_anchors(preview, payload["evidence_id"])
        if diagnostics:
            return preview, original, diagnostics
        if len(original) > MAX_READ_REFERENCES or set(original) != {
            f"n{i}" for i in range(1, len(original) + 1)
        }:
            raise ValueError("invalid_reference_registry")
        original = {
            k: ReadEvidenceAnchor.model_validate(v) for k, v in original.items()
        }
        if any(a.end - a.start > 500 for a in original.values()):
            raise ValueError("invalid_reference_registry")
        passages = tuple(EvidencePassage(**p) for p in payload["passages"])
        unit_groups = [split_quote_units((p,), []) for p in passages]
    except (ValueError, TypeError, KeyError):
        return preview, dict(references), ["invalid_read_reference_preview"]
    proposed = dict(original)
    rows = []
    group_sizes = []
    for units in unit_groups:
        before = len(rows)
        previous = dict(proposed)
        for unit in units:
            anchor = ReadEvidenceAnchor(
                **{
                    k: getattr(unit, k)
                    for k in ("evidence_id", "version", "content_hash", "start", "end")
                }
            )
            ref = next((k for k, a in proposed.items() if a == anchor), None)
            if ref is None:
                if len(proposed) >= MAX_READ_REFERENCES:
                    diagnostics.append("read_reference_capacity")
                    break
                ref = f"n{len(proposed) + 1}"
                proposed[ref] = anchor
            # Source identity is already in the envelope. Repeating its long hash
            # for every citation can evict the actual conditional text.
            rows.append(
                {"ref": ref, "start": unit.start, "end": unit.end, "text": unit.text}
            )
        if len(rows) - before != len(units):
            del rows[before:]
            proposed = previous
        else:
            group_sizes.append(len(units))

    def render():
        return json.dumps(
            {
                **payload,
                "passages": rows,
                "selection": {
                    **payload["selection"],
                    "omitted": payload["selection"].get("omitted", False)
                    or sum(len(p["text"]) for p in rows)
                    != sum(len(p.text) for p in passages),
                },
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )

    while len(render()) > 4000 and group_sizes:
        del rows[-group_sizes.pop() :]
        diagnostics.append("read_reference_omitted")
    rendered = render()
    if len(rendered) > 4000:
        return preview, original, ["read_reference_context_limit"]
    surviving = {p["ref"] for p in rows}
    return (
        rendered,
        {k: v for k, v in proposed.items() if k in original or k in surviving},
        list(dict.fromkeys(diagnostics)),
    )


async def resolve_recorded_findings(arguments, *, task, references, existing, context):
    arguments = RecordFindingsArguments.model_validate(arguments.model_dump())
    working = [Finding.model_validate(f.model_dump()) for f in existing]
    sources = {}
    for draft in arguments.findings:
        supports = []
        for ref in draft.refs:
            if ref not in references:
                raise ValueError("invalid_read_reference")
            anchor = ReadEvidenceAnchor.model_validate(references[ref])
            if anchor.evidence_id not in task.authorized_evidence_ids:
                raise ValueError("evidence_not_authorized")
            if anchor.evidence_id not in sources:
                try:
                    record = await context.evidence_store.get(
                        context.workspace_id, anchor.evidence_id
                    )
                    body = await context.evidence_store.read_body(
                        context.workspace_id, anchor.evidence_id
                    )
                except KeyError as exc:
                    raise ValueError("evidence_unavailable") from exc
                sources[anchor.evidence_id] = record, body
            record, body = sources[anchor.evidence_id]
            if (
                record.status is not EvidenceLifecycleStatus.ACTIVE
                or anchor.version != record.version
                or anchor.content_hash != record.content_hash
                or anchor.end > len(body)
                or not 1 <= anchor.end - anchor.start <= 500
            ):
                raise ValueError("invalid_read_reference_source")
            supports.append(
                EvidenceSupport(
                    **anchor.model_dump(), quote=body[anchor.start : anchor.end]
                )
            )
        keys = sorted(
            [s.evidence_id, s.version, s.content_hash, s.start, s.end] for s in supports
        )
        identity = [
            task.run_id,
            task.thread_id,
            task.caller_id,
            task.query,
            draft.claim,
            keys,
        ]
        digest = hashlib.sha256(
            json.dumps(identity, ensure_ascii=False, separators=(",", ":")).encode()
        ).hexdigest()[:32]
        finding = Finding(
            id="research-" + digest,
            claim=draft.claim,
            confidence=draft.confidence,
            evidence_ids=list(dict.fromkeys(s.evidence_id for s in supports)),
            supports=supports,
        )
        if finding.id not in {f.id for f in working}:
            working.append(finding)
        if len(working) > MAX_RESEARCH_FINDINGS:
            raise ValueError("research_finding_capacity")
    return working
