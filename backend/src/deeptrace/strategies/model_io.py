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
