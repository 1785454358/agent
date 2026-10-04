"""Shared deterministic model-output parsing helpers for strategy nodes."""

from __future__ import annotations

# Public decoding imports are retained for existing consumers, including eval.
from deeptrace.harness.model_io import parse_json_object, payload_text

__all__ = [
    "branch_context",
    "conversation_background_lines",
    "parse_json_object",
    "payload_text",
    "research_messages",
]


def conversation_background_lines(research_input) -> list[str]:
    """Bounded conversation background for strategy prompts."""
    summary = research_input.conversation_summary
    lines = (
        ([f"主题：{summary.topic}"] if summary.topic else [])
        + [f"约束：{c}" for c in summary.user_constraints[:5]]
        + [f"已知：{f}" for f in summary.established_facts[:5]]
        + [f"最近对话：{m}" for m in research_input.recent_messages[:4]]
    )
    return lines


def branch_context(state):
    """Carry the original task and all current constraints into every branch."""
    summary = state.get("conversation_summary") or {}
    if hasattr(summary, "model_dump"):
        summary = summary.model_dump()
    return {
        "original_task": state.get("question") or state.get("original_task", ""),
        "constraints": list(
            summary.get("user_constraints") or state.get("constraints") or []
        ),
        "context_notes": list(state.get("context_notes") or [])
        + list(summary.get("established_facts") or [])
        + list(state.get("recent_messages") or []),
        "requirements": list(state.get("requirements") or [])[:6],
        "evidence_contract_version": state.get("evidence_contract_version", 1),
        "target_requirement_ids": list(state.get("target_requirement_ids") or [])[:6],
        "research_gaps": [
            gap[:500]
            for gap in (
                state.get("research_gaps") or state.get("unresolved_gaps") or []
            )[:6]
        ],
    }


def assigned_targets(state, query):
    """Validated supplement responsibility overrides initial responsibility."""
    for field in ("supplement_targets", "query_targets"):
        mapping = state.get(field) or {}
        if query in mapping:
            return list(mapping[query])
    return list(state.get("target_requirement_ids") or [])


def parent_evidence_candidates(state):
    """Only host-selected conversation/parent results, never arbitrary grants."""
    return list(
        dict.fromkeys(
            [
                *(state.get("prior_evidence_ids") or []),
                *(state.get("evidence_ids") or []),
            ]
        )
    )[:100]


def research_messages(research_input, prompt):
    from deeptrace.harness.prompts import task_messages

    return task_messages(
        instruction="按当前研究阶段完成规划或评估，遵守用户约束与输出契约。",
        task=research_input.question,
        constraints=research_input.conversation_summary.user_constraints,
        prompt=prompt,
    )
