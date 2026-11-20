"""Observed acquisition failures are recovery hints, never new fact requirements."""

_ACTIONS = {
    "discovery": "改用目标实体、条件或原文术语检索，寻找不同候选来源。",
    "fetch": "搜索可读取的原始来源或替代页面，避免重复抓取已失败的同一URL。",
    "read": "从已有授权正文按缺失要点定位其他完整原文，再决定是否需要新来源。",
    "context": "先定向读取已有正文中缺失的完整条件，减少重复片段；省略不代表原文不存在。",
    "validation": "核对实际可见引用、来源身份和版本；校验拒绝不等于搜索没有结果。",
}


def acquisition_diagnostics(state):
    rows, seen = [], set()

    def add(stage, reason, query=""):
        key = (stage, reason, query)
        if key not in seen and len(rows) < 24:
            rows.append(
                {
                    "stage": stage,
                    "reason": reason[:160],
                    "query": query[:120],
                    "next_action": _ACTIONS[stage],
                }
            )
            seen.add(key)

    def classify(code, query=""):
        if code.startswith(
            (
                "synthesis_window_",
                "read_anchor_omitted",
                "read_reference_omitted",
                "evaluation_context_",
                "quote_unit_capacity",
            )
        ):
            add("context", code, query)
        elif code.startswith(
            (
                "invalid_support",
                "invalid_read",
                "invalid_requirement",
                "invalid_research_result",
                "evaluation_unavailable",
            )
        ):
            add("validation", code, query)
        elif code.startswith("unread_evidence:"):
            add("read", code, query)

    for outcome in [
        *(state.get("topic_outcomes") or []),
        *(state.get("researcher_outcomes") or []),
    ]:
        for error in outcome.errors:
            add(
                "discovery" if error.stage == "search" else error.stage,
                error.code,
                outcome.query,
            )
        for code in [
            *outcome.read_anchor_diagnostics,
            *outcome.research_finding_diagnostics,
        ]:
            classify(code, outcome.query)
        if (
            not outcome.errors
            and not outcome.evidence_ids
            and "batch_acquisition_incomplete" in outcome.research_finding_diagnostics
        ):
            add(
                "fetch" if outcome.attempted_urls else "discovery",
                "no_usable_source",
                outcome.query,
            )
    for code in (state.get("diagnostic_gaps") or [])[:100]:
        classify(code)
    return rows
