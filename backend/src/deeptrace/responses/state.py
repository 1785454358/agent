"""Graph state for the response subgraphs."""

from __future__ import annotations

from typing import TypedDict

from deeptrace.domain import Evidence, ResponseInput, ResponseOutcome
from deeptrace.responses.models import ResponseDraft


class ResponseState(TypedDict, total=False):
    response_input: ResponseInput
    loaded_evidence: list[Evidence]
    draft: ResponseDraft | None
    visible_evidence_ids: list[str]
    grounding_issue: str | None
    outcome: ResponseOutcome | None
