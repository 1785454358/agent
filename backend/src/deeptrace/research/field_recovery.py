"""Field-directed recovery of current originals through the normal read path."""

import hashlib
import json
import re

from deeptrace.domain import CoverageAssessment, EvidenceLifecycleStatus, Finding, ResearchMode
from deeptrace.domain.evidence_anchor import ReadEvidenceAnchor
from deeptrace.research.observations import field_supports
from deeptrace.strategies.source_reread import SourceReadAction
from deeptrace.tools.evidence_views import _matches, _source_blocks, _terms

FIELD_QUERIES = {
    "budget": "maximum length tokens sample sampling responses FLOPs inference compute budget evaluation",
    "model": "model architecture parameters base pretrained experimental setup",
    "dataset": "dataset benchmark evaluation test split subset",
    "result": "results score accuracy performance evaluation",
    "metric": "metric accuracy pass rating evaluation",
    "conditions": "conditions limitations protocol assumptions sampling temperature",
}
FIELD_PATTERNS = {"budget": r"预算|计算量|开销|\bbudget\b|\bcompute\b",
    "model": r"模型|基座|\bmodel", "dataset": r"评测集|数据集|基准|\bdataset|\bbenchmark",
    "result": r"结果|成绩|\bresult|\bscore", "metric": r"指标|\bmetric",
    "conditions": r"实验条件|实验口径|\bconditions|\bprotocol"}


def checked_requirement_ids(checks, findings):
    if not checks:
        return set()
    versions={(s.evidence_id,s.version,s.content_hash) for raw in findings
              for s in Finding.model_validate(raw).supports}
    return {identity for c in checks if c.get("status")=="read_unresolved"
        and (c.get("evidence_id"),c.get("version"),c.get("content_hash")) in versions
        and c.get("ranges") and all(0<=a<b and b-a<=900 for a,b in c["ranges"])
        for identity in c.get("target_requirement_ids",[])}


def field_gaps(state):
    if (state.get("research_brief") or {}).get("source_policy") != "research_results":
        return []
    requested=[]
    for requirement in state.get("requirements",[]):
        analytical=re.search(r"机制|作用|为什么|为何|原因|建议|选型|如何|解释",requirement.description)
        listing=re.search(r"列出|列明|各.{0,20}(?:研究|论文).{0,10}模型|实验设置|参数表",requirement.description)
        if requirement.required and (not analytical or listing):
            requested.append(requirement)
    targets = {name: [r.id for r in requested
        if re.search(FIELD_PATTERNS[name], r.description, re.I)] for name in FIELD_QUERIES}
    gaps = []
    for finding in state.get("findings", []):
        if finding.research_result is None or finding.research_result.kind=="original_theory":
            continue
        for experiment in finding.experiments or [None]:
            context = " ".join(getattr(experiment, name).value for name in ("model", "dataset", "conditions")
                if experiment is not None and getattr(experiment, name) is not None)
            model_quotes = field_supports(finding, experiment.model) if experiment else []
            identity = model_quotes[0].evidence_id if model_quotes else finding.evidence_ids[0]
            for name in FIELD_QUERIES:
                if not targets[name] or (experiment is not None and getattr(experiment, name) is not None):
                    continue
                key = hashlib.sha256(json.dumps([identity, context, name], ensure_ascii=False).encode()).hexdigest()[:24]
                gaps.append({"key": key, "evidence_id": identity, "field": name,
                    "context": context, "target_requirement_ids": targets[name]})
    return sorted(gaps, key=lambda g: list(FIELD_QUERIES).index(g["field"]))


async def plan_field_reads(state, context):
    checks = list(state.get("field_checks") or [])[-48:]
    actions, planned = [], set()
    if state.get("field_reread_count", 0) >= 2 or getattr(context.model_gateway, "research_exhausted", False):
        return {"reread_actions": [], "field_checks": checks}
    for gap in field_gaps(state):
        identity = gap["evidence_id"]
        if (state.get("source_eligibility") or {}).get(identity) != "eligible":
            continue
        try:
            record = await context.evidence_store.get(context.workspace_id, identity)
            if record.status is not EvidenceLifecycleStatus.ACTIVE:
                continue
            if any(c.get("key") == gap["key"] and c.get("version") == record.version
                and c.get("content_hash") == record.content_hash for c in checks):
                continue
            body = await context.evidence_store.read_body(context.workspace_id, identity)
        except (KeyError, OSError):
            continue
        terms, subject = _terms(FIELD_QUERIES[gap["field"]]), _terms(gap["context"])
        ranked = []
        for start, end in _source_blocks(body):
            text = body[start:end].casefold()
            hits = sum(_matches(text, term) for term in terms)
            if 35 <= end-start <= 900 and hits >= 2:
                ranked.append((hits, sum(_matches(text, term) for term in subject), start, end))
        ranked.sort(key=lambda row: (-row[0], -row[1], row[2]))
        if not ranked:
            checks.append({**gap, "version": record.version, "content_hash": record.content_hash,
                "status": "no_matching_passage", "ranges": []})
            continue
        _, _, start, end = ranked[0]
        span = (identity, record.version, record.content_hash, start, end)
        if any(c.get("evidence_id")==identity and c.get("version")==record.version
               and c.get("content_hash")==record.content_hash and c.get("status")=="read_unresolved"
               and [start,end] in c.get("ranges",[]) for c in checks):
            checks.append({**gap,"version":record.version,"content_hash":record.content_hash,
                "status":"read_unresolved","ranges":[[start,end]]})
            continue
        if span in planned:
            continue
        planned.add(span)
        actions.append(SourceReadAction(anchor=ReadEvidenceAnchor(evidence_id=identity,
            version=record.version, content_hash=record.content_hash, start=start, end=end),
            target_requirement_ids=gap["target_requirement_ids"]))
        checks.append({**gap, "version": record.version, "content_hash": record.content_hash,
            "status": "unread", "ranges": [[start, end]]})
        if len(actions) == 2:
            break
    return {"reread_actions": actions, "field_checks": checks[-48:]}


async def field_reread_node(state, runtime):
    from deeptrace.strategies.workflow.reread import reread_node
    from deeptrace.research.execution import caller_for_mode
    plan = {"reread_actions": state["field_actions"], "field_checks": list(state.get("field_checks") or [])} \
        if state.get("field_actions") else await plan_field_reads(state, runtime.context)
    if not plan["reread_actions"]:
        return {"field_actions": [], "field_checks": plan["field_checks"],
            "field_reread_count": state.get("field_reread_count", 0) + 1}
    # Reuse the authorized tool path and successful-gapless-anchor checks.
    mode = ResearchMode(state.get("mode", "workflow"))
    result = await reread_node({**state, "coverage": CoverageAssessment.model_validate(state["coverage"]), "reread_attempted": False,
        "reread_actions": plan["reread_actions"]}, runtime,
        mode=mode, caller_id=caller_for_mode(mode))
    anchors = [a for o in result.get("topic_outcomes", []) for a in o.read_anchors]
    for check in plan["field_checks"]:
        if check["status"] != "unread":
            continue
        check["status"] = "read_unresolved" if any(a.evidence_id == check["evidence_id"]
            and a.version == check["version"] and a.content_hash == check["content_hash"]
            and [a.start,a.end] in check["ranges"] for a in anchors) else "unavailable"
    result.pop("reread_attempted", None)
    result.pop("reread_actions", None)
    result["reread_queries"] = list(dict.fromkeys([*(state.get("reread_queries") or []), *result.get("reread_queries", [])]))
    return {**result, "field_actions": [], "field_checks": plan["field_checks"],
        "field_reread_count": state.get("field_reread_count", 0) + 1}
