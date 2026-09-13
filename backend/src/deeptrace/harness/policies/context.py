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


SUMMARY_FACT_LIMIT = 30
SUMMARY_LIST_LIMIT = 20
SUMMARY_ENTITY_LIMIT = 30


def merge_summaries(
    left: "ConversationSummary", right: "ConversationSummary"
) -> "ConversationSummary":
    """Bounded, deterministic merge used by every compression round."""
    from deeptrace.domain import ConversationSummary

    def extend(previous: list[str], incoming: list[str], limit: int) -> list[str]:
        merged = list(previous)
        for value in incoming:
            if value and value not in merged:
                merged.append(value)
            if len(merged) >= limit:
                break
        return merged[:limit]

    entities = dict(left.referenced_entities)
    for key, value in right.referenced_entities.items():
        if key not in entities:
            entities[key] = value
        if len(entities) >= SUMMARY_ENTITY_LIMIT:
            break
    return ConversationSummary(
        topic=right.topic or left.topic,
        user_constraints=extend(left.user_constraints, right.user_constraints, SUMMARY_LIST_LIMIT),
        established_facts=extend(left.established_facts, right.established_facts, SUMMARY_FACT_LIMIT),
        referenced_entities=entities,
        unresolved_questions=extend(left.unresolved_questions, right.unresolved_questions, SUMMARY_LIST_LIMIT),
        previous_conclusions=extend(left.previous_conclusions, right.previous_conclusions, SUMMARY_LIST_LIMIT),
    )
