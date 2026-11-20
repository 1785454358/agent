"""Task metadata and model input estimates independent of a domain prompt."""

import json
from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from deeptrace.harness.token_budget import count_tokens


class TaskContext(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task: str = Field(min_length=1)
    constraints: list[str]


def message_tokens(messages: list[Any], tools: Sequence[Any] = ()) -> int:
    payload = [message.model_dump(mode="json") for message in messages]
    return count_tokens(json.dumps([payload, tools], ensure_ascii=False, default=str))


def prompt_segment_estimates(messages):
    """Text-only local estimates, not an additive provider billing ledger."""
    parts = {"rules": [], "schema": [], "evidence": [], "task_and_history": []}
    for message in messages:
        content = str(message.content)
        if message.type == "system":
            before, marker, after = content.partition("JSON Schema：\n")
            parts["rules"].append(before)
            if marker:
                try:
                    value, end = json.JSONDecoder().raw_decode(after)
                    parts["schema"].append(after[:end])
                    parts["rules"].append(after[end:])
                except ValueError:
                    parts["rules"].append(after)
        else:
            before, marker, after = content.partition("EVIDENCE_VIEW_JSON:")
            parts["task_and_history"].append(before)
            if marker:
                parts["evidence"].append(after)
    return {key: count_tokens("\n".join(values)) for key, values in parts.items()}
