"""Model response decoding shared by the session and research strategies."""

from __future__ import annotations

import json
from typing import Any


def payload_text(response: Any) -> str:
    content = (
        response
        if isinstance(response, str)
        else getattr(response, "content", response)
    )
    if isinstance(content, list):
        content = "\n".join(
            part if isinstance(part, str) else part.get("text", "")
            for part in content
            if isinstance(part, (str, dict))
        )
    stripped = str(content).strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()[1:]
        if lines and lines[-1].strip().endswith("```"):
            lines.pop()
        stripped = "\n".join(lines).strip()
    return stripped


def parse_json_object(text: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(text)
    except (TypeError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None
