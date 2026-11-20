"""Controller quality policy around the existing evidence evaluator."""

from deeptrace.strategies.evaluation_retention import retain_verified_findings
from deeptrace.strategies.workflow.nodes import evaluate_node as evaluate_current


async def _evaluate_sources(state, runtime):
    # The host already removes rejected supports and normalizes coverage.
    # Spend recovery on missing facts, not a second opinion on the same data.
    # Schema failures and unauthorized source restrictions can still repair.
    result = await evaluate_current(state, runtime, repair_source_admission=False)
    return await retain_verified_findings(state, result, runtime)


async def evaluate_node(state, runtime):
    from deeptrace.research.field_recovery import field_gaps, plan_field_reads
    from deeptrace.research.verification import verify_evidence_graph
    result = await _evaluate_sources(state, runtime)
    combined = {**state, **result}
    gaps = field_gaps(combined)
    if not gaps or result.get("evaluation") is None:
        return {**result, "field_actions": []}
    plan = await plan_field_reads(combined, runtime.context)
    requirements={r.id:r for r in state["requirements"]}
    versions={(r.id,r.version,r.content_hash) for r in result["verification"].graph.evidence} if result.get("verification") else set()
    items=[]
    for item in result["coverage"].items:
        local=[g for g in gaps if item.requirement_id in g["target_requirement_ids"]]
        if not local:
            items.append(item)
            continue
        checked=all(any(c.get("key")==gap["key"] and c.get("status")=="read_unresolved"
            and (c.get("evidence_id"),c.get("version"),c.get("content_hash")) in versions
            for c in plan["field_checks"]) for gap in local)
        notes=[f"{gap['field']}: {gap['context']} 本次检查范围内未核实"[:300] for gap in local]
        if checked and requirements[item.requirement_id].allow_unknown and item.finding_ids:
            items.append(item.model_copy(update={"status":"covered","resolution":"not_found",
                "reason":"answered_with_disclosed_limitations","unanswered_parts":[],
                "limitations":list(dict.fromkeys([*item.limitations,*notes]))[:6]}))
        else:
            items.append(item.model_copy(update={"status":"missing","reason":"required_experiment_field_unverified",
                "unanswered_parts":list(dict.fromkeys([*item.unanswered_parts,*notes]))[:6]}))
    coverage = result["coverage"].model_copy(update={"items": items})
    assessment = result["evaluation"].model_copy(update={"coverage": coverage, "sufficient": False})
    verification = result.get("verification")
    if verification is not None:
        verification = verify_evidence_graph(verification.graph, state["requirements"], submitted_coverage=coverage)
    return {**result, "coverage": coverage, "evaluation": assessment, "verification": verification,
        "field_actions": plan["reread_actions"], "field_checks": plan["field_checks"],
        "unresolved_gaps": [f"{i.requirement_id}:{i.reason}" for i in coverage.items if i.status != "covered"]}
