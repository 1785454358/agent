"""Shared deterministic model-output parsing helpers for strategy nodes."""

from __future__ import annotations

import json
from typing import Any


def payload_text(response: Any) -> str:
    """Extract comparable text from a model gateway response."""
    if isinstance(response, str):
        text = response
    elif hasattr(response, "content"):
        content = response.content
        text = content if isinstance(content, str) else str(content)
    else:
        text = str(response)
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 2 and lines[-1].strip().endswith("```"):
            lines = lines[1:-1]
        elif lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        stripped = "\n".join(lines).strip()
    return stripped


def parse_json_object(text: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(text)
    except (TypeError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


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
        "constraints": list(summary.get("user_constraints") or state.get("constraints") or []),
        "context_notes": list(summary.get("established_facts") or []) + list(state.get("recent_messages") or []),
    }


def research_messages(research_input, prompt):
    from deeptrace.harness.prompts import task_messages
    return task_messages(instruction="按当前研究阶段完成规划或评估，遵守用户约束与输出契约。",
                         task=research_input.question,
                         constraints=research_input.conversation_summary.user_constraints, prompt=prompt)
