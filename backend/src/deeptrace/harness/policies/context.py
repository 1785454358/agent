"""Sliding-window context policy for the short-term conversation state."""

from __future__ import annotations

from typing import Any


SOFT_MESSAGE_LIMIT = 24
HARD_MESSAGE_LIMIT = 60


def plan_context_window(
    messages: list[Any],
    *,
    soft_limit: int = SOFT_MESSAGE_LIMIT,
    hard_limit: int = HARD_MESSAGE_LIMIT,
) -> tuple[list[Any], list[Any]]:
    """Keep the most recent window; return (kept, overflow) in stable order."""
    if not messages:
        return [], []
    limit = min(hard_limit, max(soft_limit, 0)) or soft_limit
    if hard_limit < len(messages):
        kept = list(messages[-hard_limit:])
    elif soft_limit < len(messages):
        kept = list(messages[-soft_limit:])
    else:
        kept = list(messages)
    overflow = list(messages[: len(messages) - len(kept)])
    return kept, overflow
