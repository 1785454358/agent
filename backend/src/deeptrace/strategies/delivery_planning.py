"""Resolve selected-solution references and allocate actual discovery queries."""

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from deeptrace.domain.delivery import DeliveryPlan


class DeliveryRevision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plan: DeliveryPlan
    reason: str = Field(min_length=1, max_length=600)
    finding_ids: list[str] = Field(default_factory=list, max_length=12)


def revise_delivery(state, payload):
    """Revisions cannot remove sealed needs or cite unverified model claims."""
    raw = (payload or {}).get("delivery_revision")
    if raw is None:
        return {}
    try:
        previous = state.get("delivery_plan")
        if previous is None:
            raise ValueError("no_selected_solution")
        revision = DeliveryRevision.model_validate(raw)
        if not revision.reason.strip():
            raise ValueError("empty_revision_reason")
        if {n.requirement_id for n in revision.plan.evidence_needs} != {r.id for r in state["requirements"]}:
            raise ValueError("changed_user_requirements")
        verification = state.get("verification")
        accepted = {c.id for c in verification.accepted_claims} if verification else set()
        if not set(revision.finding_ids) <= accepted:
            raise ValueError("unverified_revision_basis")
        history = list(state.get("delivery_plan_history") or [])
        if len(history) >= 6:
            raise ValueError("revision_limit")
        if revision.plan == previous:
            return {}
        from deeptrace.domain import CoverageAssessment, RequirementCoverage

        coverage = CoverageAssessment(items=[RequirementCoverage(
            requirement_id=r.id, status="missing", reason="solution_revision_requires_revalidation",
        ) for r in state["requirements"]])
        return {
            "delivery_plan": revision.plan,
            "delivery_plan_history": [*history, {
                "plan": previous.model_dump(mode="json"), "reason": revision.reason,
                "finding_ids": revision.finding_ids,
            }],
            # Old factual findings survive, but their former applicability to
            # this changed solution must be assessed again, not inherited.
            "coverage": coverage,
            "verification": verification.model_copy(update={"coverage": coverage}) if verification else None,
            "diagnostic_gaps": ["delivery_plan_revised"],
        }
    except (ValidationError, ValueError, TypeError):
        return {"diagnostic_gaps": ["delivery_revision_rejected"]}


def seal_delivery_plan(payload, proposed, requirements):
    raw = (payload or {}).get("delivery_plan")
    if raw is None:
        return None, []
    try:
        plan = DeliveryPlan.model_validate(raw)
        if not proposed or len(proposed) != len(requirements):
            raise ValueError("missing_requirement_mapping")
        remap = {old.id: new.id for old, new in zip(proposed, requirements, strict=True)}
        if len(remap) != len(proposed) or {n.requirement_id for n in plan.evidence_needs} != set(remap):
            raise ValueError("incomplete_evidence_needs")
        plan = DeliveryPlan.model_validate({
            **plan.model_dump(),
            "evidence_needs": [{"requirement_id": remap[n.requirement_id], "query": n.query.strip()}
                               for n in plan.evidence_needs],
        })
    except (ValidationError, ValueError, TypeError):
        return None, ["initial_delivery_plan_degraded"]
    return plan, []


def discovery_from_delivery(plan: DeliveryPlan, requirements, *, limit: int):
    """Every need gets a search seed, within the existing two-seed task cap."""
    if not 1 <= limit <= 6 or len(plan.evidence_needs) > 2 * limit:
        raise ValueError("delivery_query_capacity")
    descriptions = {r.id: r.description for r in requirements}
    if {n.requirement_id for n in plan.evidence_needs} != set(descriptions):
        raise ValueError("delivery_requirement_mismatch")
    groups = [[] for _ in range(min(limit, len(plan.evidence_needs)))]
    for index, need in enumerate(plan.evidence_needs):
        groups[index % len(groups)].append(need)
    targets, briefs = {}, {}
    for group in groups:
        query = group[0].query
        targets[query] = [n.requirement_id for n in group]
        briefs[query] = {
            "objective": plan.approach,
            "boundary": "; ".join(descriptions[n.requirement_id] for n in group)[:600],
            "source_strategy": "遵守原始用户资料范围，核实选定方案的必要事实；报价保留日期与适用条件。",
            "expected_output": "对应需求的原文依据、适用条件和具体缺口；不调查未选候选。",
            "search_queries": [n.query for n in group],
        }
    return {"queries": list(targets), "query_targets": targets, "task_briefs": briefs}
