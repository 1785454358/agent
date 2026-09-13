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
