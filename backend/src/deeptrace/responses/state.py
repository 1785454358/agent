"""Graph state for the response subgraphs."""

from __future__ import annotations

from typing import TypedDict

from deeptrace.domain import Evidence, ResponseInput, ResponseOutcome
from deeptrace.responses.models import ResponseDraft


class ResponseState(TypedDict, total=False):
    response_input: ResponseInput
    loaded_evidence: list[Evidence]
    draft: ResponseDraft | None
    outcome: ResponseOutcome | None
