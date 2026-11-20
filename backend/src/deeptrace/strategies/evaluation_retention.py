"""Revalidate prior accepted work when a bounded reassessment cannot see it."""

import hashlib

from deeptrace.domain import EvidenceLifecycleStatus
from deeptrace.research.verification import project_verification_result


async def retain_verified_findings(state, result, runtime, *, assessment_key="evaluation"):
    visible = set(result.pop("evaluated_evidence_ids", []))
    previous = state.get("verification")
    if previous is None:
        return result
    failed = result.get(assessment_key) is None
    # A source omitted from this call has not been reassessed. Keep its old
    # verified work only after checking the current body/version again. Never
    # carry old coverage forward as a verdict on the new material window.
    accepted = {claim.id for claim in previous.accepted_claims}
    retained = [finding for finding in state.get("findings", []) if finding.id in accepted
                and (failed or any(identity not in visible for identity in finding.evidence_ids))]
    old_records = {record.id: record for record in previous.graph.evidence}
    # Source admission has its own lifecycle. A bad claim/coverage envelope
    # cannot revoke previously admitted, unchanged originals just because they
    # produced no accepted claim (e.g. a study does not establish a ranking).
    admitted_ids = [identity for identity in old_records
                    if (failed or identity not in visible)
                    and (state.get("source_eligibility") or {}).get(identity) == "eligible"]
    if not retained and not admitted_ids:
        return result
    findings = {finding.id: finding for finding in result.get("findings", [])}
    for finding in retained:
        if finding.id in findings and findings[finding.id] != finding:
            # Model labels are local to each assessment. A reused label cannot
            # overwrite an unrelated accepted fact or change current coverage.
            identity = "retained-" + hashlib.sha256(finding.model_dump_json().encode()).hexdigest()[:24]
            finding = finding.model_copy(update={"id": identity})
        findings[finding.id] = finding
    context = runtime.context
    records, bodies = [], {}
    eligibility = dict(result.get("source_eligibility") or {})
    identities = dict.fromkeys([*(identity for finding in findings.values() for identity in finding.evidence_ids),
                                *admitted_ids])
    for identity in identities:
        try:
            record = await context.evidence_store.get(context.workspace_id, identity)
            bodies[identity] = await context.evidence_store.read_body(context.workspace_id, identity)
        except KeyError:
            continue
        records.append(record)
        old = old_records.get(identity)
        if (old is not None and (failed or identity not in visible)
                and record.status is EvidenceLifecycleStatus.ACTIVE
                and (record.version, record.content_hash) == (old.version, old.content_hash)):
            eligibility[identity] = (state.get("source_eligibility") or {}).get(identity, "uncertain")
    verification = project_verification_result(
        evidence=records, bodies=bodies, findings=findings.values(),
        source_eligibility=eligibility, requirements=state["requirements"],
        coverage=result["coverage"], can_replan=False,
    )
    valid = {claim.id for claim in verification.accepted_claims}
    return {**result, "verification": verification, "source_eligibility": eligibility,
            "findings": [finding for identity, finding in findings.items() if identity in valid],
            "diagnostic_gaps": [*result.get("diagnostic_gaps", []), "prior_findings_revalidated"]}
