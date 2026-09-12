"""Strict model-output contract for response generation."""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from deeptrace.domain import ResponseMode
from deeptrace.domain.response import MAX_RESPONSE_CONTENT_LENGTH


DraftContent = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=MAX_RESPONSE_CONTENT_LENGTH,
    ),
]


class ResponseDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    response_mode: ResponseMode
    content: DraftContent
