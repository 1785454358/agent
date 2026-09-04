"""Public run events emitted by the Basic research pipeline."""

from __future__ import annotations

from pydantic import BaseModel, Field


class RunEvent(BaseModel):
    """A serializable progress event for API, SSE, and CLI consumers."""

    event_type: str
    message: str
    details: dict[str, str | int | float | bool | None] = Field(
        default_factory=dict
    )
