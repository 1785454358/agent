"""Evidence-driven evaluation coordination shared by the three strategies.

Scheduling state is not new evidence. Accepted coverage survives a delta only
after explicit impact acknowledgement and fresh host dependency validation.
"""

from copy import deepcopy
import hashlib
import json

from deeptrace.domain import CoverageAssessment, EvidenceLifecycleStatus
from deeptrace.research import project_verification_result
from deeptrace.strategies.evaluation_snapshot import _encode, evaluation_scope
from deeptrace.tools.evidence_views import _merge as merge_ranges


def _digest(value):
    return hashlib.sha256(json.dumps(value, default=_encode, ensure_ascii=False,
        sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _outcomes(state):
    return [*(state.get("topic_outcomes") or []), *(state.get("researcher_outcomes") or [])]


async def _materials(state, context, scope, known_reads=()):
    if not scope:
        return None
    try:
        inventory, versions = {}, {}
        for identity in sorted(set(state.get("evidence_ids") or [])):
            if context.source_evidence_ids is not None and identity not in context.source_evidence_ids:
                continue
            try:
                record = await context.evidence_store.get(context.workspace_id, identity)
                body = await context.evidence_store.read_body(context.workspace_id, identity)
                inventory[identity] = _digest([record, hashlib.sha256(body.encode()).hexdigest()])
                versions[identity] = (record.version, record.content_hash, len(body))
            except KeyError:
                inventory[identity] = "missing"
        observed = [a.range_key for outcome in _outcomes(state) for a in outcome.read_anchors]
        candidates = [(s.evidence_id,s.version,s.content_hash,s.start,s.end)
                      for outcome in _outcomes(state) for finding in outcome.research_findings for s in finding.supports]
        groups = {}
        for identity, version, content_hash, start, end in [*known_reads, *observed, *candidates]:
            current = versions.get(identity)
            if current and (version, content_hash) == current[:2] and 0 <= start < end <= current[2]:
                groups.setdefault((identity, version, content_hash), []).append((start,end))
        anchors = sorted([*prefix,a,b] for prefix, ranges in groups.items() for a,b in merge_ranges(ranges))
        preferred = sorted({a.range_key for outcome in _outcomes(state)
                            if outcome.query in (state.get("reread_queries") or []) for a in outcome.read_anchors})
        verification = state.get("verification")
        verified_ids = sorted(c.id for c in verification.accepted_claims) if verification is not None else []
        key = _digest([scope, inventory, anchors, preferred, state.get("findings"),
                       state.get("coverage"), state.get("source_eligibility"), verified_ids])
        return {"key": key, "sources": inventory, "read_keys": anchors}
    except (TypeError, ValueError):
        return None


def _delta(state, snapshot, materials):
    previous = snapshot.get("materials") or {}
    old_sources, current = previous.get("sources") or {}, materials["sources"]
    # Source withdrawal, provenance or body/version change requires a fresh
    # baseline. A new source is assessed for cross-requirement impact below.
    if not old_sources or any(current.get(k) != v for k, v in old_sources.items()):
        return None
    old = snapshot.get("result") or {}
    verification, coverage = old.get("verification"), old.get("coverage")
    if verification is None or coverage is None or old.get("assessment") is None:
        return None
    if coverage != state.get("coverage") or old.get("source_eligibility") != state.get("source_eligibility"):
        return None
    current_verification = state.get("verification")
    if current_verification is None:
        return None
    accepted = {claim.id for claim in verification.accepted_claims} & {c.id for c in current_verification.accepted_claims}
    current_findings = {f.id: f for f in state.get("findings") or []}
    findings = {f.id: f for f in old.get("findings") or [] if f.id in accepted and current_findings.get(f.id) == f}
    stable = [row for row in coverage.items if row.status == "covered" and row.finding_ids
              and set(row.finding_ids) <= findings.keys()]
    pending = {r.id for r in state["requirements"]} - {row.requirement_id for row in stable}
    if not stable or not pending:
        return None
    old_reads = previous.get("read_keys") or []
    def known(row):
        return any(row[:3] == old[:3] and old[3] <= row[3] and row[4] <= old[4] for old in old_reads)
    new_anchors = [a for outcome in _outcomes(state) for a in outcome.read_anchors if not known(list(a.range_key))]
    changed_ids = (current.keys() - old_sources.keys()) | {row[0] for row in materials["read_keys"] if not known(row)}
    if not changed_ids:
        return None
    partial_ids = {identity for row in coverage.items if row.requirement_id in pending
                   for finding_id in row.finding_ids if finding_id in findings
                   for identity in findings[finding_id].evidence_ids}
    descriptions = {r.id: r.description for r in state["requirements"]}
    prior = [{"requirement_id": row.requirement_id,
              "description": descriptions[row.requirement_id],
              "findings": [{"id": identity, "claim": findings[identity].claim}
                           for identity in row.finding_ids]}
             for row in stable]
    return {"requirement_ids": pending, "evidence_ids_override": sorted(changed_ids | partial_ids),
            "read_anchors_override": new_anchors, "prior_verified_requirements": prior,
            "stable": stable, "accepted_findings": findings}


async def _merge(state, context, fresh, delta, schema, incomplete_action):
    assessment = fresh.get("assessment")
    unchanged = getattr(assessment, "unchanged_requirement_ids", None)
    stable_ids = {row.requirement_id for row in delta["stable"]}
    if (assessment is None or unchanged is None or len(unchanged) != len(set(unchanged))
            or set(unchanged) != stable_ids):
        return None
    retained_ids = {identity for row in delta["stable"] for identity in row.finding_ids}
    retained = {identity: delta["accepted_findings"][identity] for identity in retained_ids}
    # Model finding labels are local to a call. Do not overwrite an unrelated
    # old finding or leave old coverage pointing at a new claim with that ID.
    renamed, new_findings = {}, []
    for finding in fresh["findings"]:
        if finding.id in retained and finding != retained[finding.id]:
            identity = "delta-" + _digest(finding)[:24]
            renamed[finding.id] = identity
            finding = finding.model_copy(update={"id": identity})
        new_findings.append(finding)
    fresh_rows = [row.model_copy(update={"finding_ids": [renamed.get(i, i) for i in row.finding_ids]})
                  for row in fresh["coverage"].items]
    by_id = {row.requirement_id: row for row in [*delta["stable"], *fresh_rows]}
    if set(by_id) != {r.id for r in state["requirements"]}:
        return None
    coverage = CoverageAssessment(items=[by_id[r.id] for r in state["requirements"]])
    findings = list({f.id: f for f in [*retained.values(), *new_findings]}.values())
    eligibility = {**(state.get("source_eligibility") or {}), **fresh["source_eligibility"]}
    records, bodies = [], {}
    for identity in state.get("evidence_ids") or []:
        if context.source_evidence_ids is not None and identity not in context.source_evidence_ids:
            continue
        try:
            record = await context.evidence_store.get(context.workspace_id, identity)
            body = await context.evidence_store.read_body(context.workspace_id, identity)
        except KeyError:
            continue
        if record.status is EvidenceLifecycleStatus.ACTIVE:
            records.append(record)
            bodies[identity] = body
    verification = project_verification_result(evidence=records, bodies=bodies, findings=findings,
        source_eligibility=eligibility, requirements=state["requirements"], coverage=coverage,
        can_replan="action" in schema.model_fields)
    accepted = {claim.id for claim in verification.accepted_claims}
    coverage = verification.coverage
    if coverage is None:
        return None
    complete = verification.coverage_complete
    changes = {"coverage": coverage}
    if "sufficient" in schema.model_fields:
        changes["sufficient"] = complete
    elif complete:
        changes["action"] = "complete"
    elif incomplete_action is not None:
        changes["action"] = incomplete_action
    return {**fresh, "assessment": assessment.model_copy(update=changes), "coverage": coverage,
            "findings": [f for f in findings if f.id in accepted], "source_eligibility": eligibility,
            "verification": verification,
            "unresolved_gaps": [f"{row.requirement_id}:{row.status}:{row.reason}"[:500]
                                for row in coverage.items if row.status != "covered"]}


async def _progress(state, context, result):
    from deeptrace.strategies.evidence_evaluation import current_source_records, progress_keys
    result.pop("supplement_completed", None)
    result.pop("no_progress", None)
    if state.get("progress_before_supplement") is not None:
        records = await current_source_records(state, context)
        result["supplement_completed"] = True
        result["no_progress"] = not (progress_keys(records, result["findings"], result["coverage"],
            source_eligibility=result["source_eligibility"]) - set(state["progress_before_supplement"]))


async def _unavailable_delta(state, context, fresh, schema):
    """Do not spend a larger retry after a failed bounded delta request."""
    from deeptrace.strategies.evidence_evaluation import missing_coverage, current_source_records
    coverage = missing_coverage(state["requirements"], "delta_impact_unavailable")
    records = await current_source_records(state, context)
    bodies = {r.id: await context.evidence_store.read_body(context.workspace_id, r.id) for r in records}
    verification = project_verification_result(evidence=records, bodies=bodies, findings=fresh["findings"],
        source_eligibility=fresh["source_eligibility"], requirements=state["requirements"],
        coverage=coverage, can_replan="action" in schema.model_fields)
    return {**fresh, "coverage": verification.coverage, "verification": verification,
        "unresolved_gaps": [f"{r.id}:missing:delta_impact_unavailable" for r in state["requirements"]]}


async def evaluate_incrementally(state, context, schema, **kwargs):
    from deeptrace.strategies.evidence_evaluation import _evaluate_evidence_scope, require_evidence_contract
    require_evidence_contract(state)
    scope = evaluation_scope(state, context, schema)
    snapshot = state.get("evaluation_snapshot")
    compatible = bool(scope and isinstance(snapshot, dict) and snapshot.get("scope") == scope)
    known_reads = (snapshot.get("materials") or {}).get("read_keys", []) if compatible else []
    materials = await _materials(state, context, scope, known_reads)
    mode, reason = "full", "initial_or_invalidated"
    if compatible and materials and (snapshot.get("materials") or {}).get("key") == materials["key"]:
        result = deepcopy(snapshot["result"])
        mode, reason = "reused", "no_evidence_change"
        result["diagnostic_gaps"] = list(dict.fromkeys([
            *(state.get("diagnostic_gaps") or []), *result.get("diagnostic_gaps", []),
            "evaluation_snapshot_reused"]))
    else:
        delta = (_delta(state, snapshot, materials) if compatible and materials
                 and "unchanged_requirement_ids" in schema.model_fields else None)
        if delta:
            scoped = {key: delta[key] for key in ("requirement_ids", "evidence_ids_override",
                                                  "read_anchors_override", "prior_verified_requirements")}
            fresh = await _evaluate_evidence_scope(state, context, schema, **kwargs, **scoped)
            result = (await _merge(state, context, fresh, delta, schema, kwargs.get("incomplete_action"))
                      if fresh.get("assessment") is not None else None)
            if fresh.get("assessment") is None:
                mode, reason = "delta", "delta_unavailable"
                result = await _unavailable_delta(state, context, fresh, schema)
            elif result is not None:
                mode, reason = "delta", "new_evidence_for_pending_requirements"
            else:
                # Conflicts, omitted impact checks and failed delta outputs
                # cannot validate the old verdict against the new evidence.
                mode, reason = "full", "impact_uncertain_or_changed"
                result = await _evaluate_evidence_scope(state, context, schema, **kwargs)
        else:
            result = await _evaluate_evidence_scope(state, context, schema, **kwargs)
    await _progress(state, context, result)
    observed = result.pop("evaluation_read_ranges", [])
    result["evaluation_snapshot"] = None
    if scope and result.get("assessment") is not None and result.get("verification") is not None:
        after = await _materials({**state, **result}, context, scope, [*known_reads, *observed])
        if after:
            result["evaluation_snapshot"] = {"scope": scope, "materials": after,
                "result": {key: value for key, value in result.items() if key != "evaluation_snapshot"}}
    try:
        await context.event_sink.emit("research.evaluation_scope", {"evaluation_mode": mode, "reason": reason,
            "evaluated_requirements_json": json.dumps(sorted(delta["requirement_ids"]) if mode == "delta" else
                [] if mode == "reused" else [r.id for r in state["requirements"]]),
            "retained_requirements_json": json.dumps([r.requirement_id for r in delta["stable"]]
                if mode == "delta" and reason != "delta_unavailable" else [])})
    except Exception:
        pass
    return result
