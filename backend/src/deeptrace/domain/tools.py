from __future__ import annotations

import json
from enum import StrEnum
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    StringConstraints,
    field_validator,
    model_validator,
)

from deeptrace.domain.errors import (
    classify_error_code,
    error_message_for,
    is_retryable,
)
from deeptrace.domain.execution import ErrorCategory


MAX_TOOL_ID_LENGTH = 128
MAX_TOOL_ARGUMENTS_BYTES = 32 * 1024
MAX_TOOL_PREVIEW_LENGTH = 4_000
MAX_TOOL_DATA_REF_LENGTH = 2_048
MAX_TOOL_ERROR_CODE_LENGTH = 128
MAX_TOOL_MESSAGE_LENGTH = 1_000
MAX_TOOL_EVIDENCE_IDS = 100

ToolIdentifier = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=MAX_TOOL_ID_LENGTH,
    ),
]
ErrorCode = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=MAX_TOOL_ERROR_CODE_LENGTH,
    ),
]
DataReference = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=MAX_TOOL_DATA_REF_LENGTH,
    ),
]


class ToolName(StrEnum):
    SEARCH_WEB = "search_web"
    FETCH_PAGE = "fetch_page"
    SEARCH_MEMORY = "search_memory"


def _json_size(value: JsonValue) -> int:
    try:
        serialized = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("value must be JSON-compatible") from exc
    return len(serialized.encode("utf-8"))


class _ToolCorrelation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: ToolIdentifier
    run_id: ToolIdentifier
    thread_id: ToolIdentifier
    call_id: ToolIdentifier
    tool: ToolName


class ToolRequest(_ToolCorrelation):
    arguments: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("arguments")
    @classmethod
    def bounded_arguments(
        cls,
        value: dict[str, JsonValue],
    ) -> dict[str, JsonValue]:
        if _json_size(value) > MAX_TOOL_ARGUMENTS_BYTES:
            raise ValueError(
                f"arguments exceed {MAX_TOOL_ARGUMENTS_BYTES} encoded bytes"
            )
        return value


class ToolResult(_ToolCorrelation):
    ok: bool
    error_code: ErrorCode | None = None
    error_category: ErrorCategory | None = None
    retryable: bool = False
    message: str | None = Field(default=None, max_length=MAX_TOOL_MESSAGE_LENGTH)
    preview: str = Field(default="", max_length=MAX_TOOL_PREVIEW_LENGTH)
    data_ref: DataReference | None = None
    evidence_ids: list[ToolIdentifier] = Field(
        default_factory=list,
        max_length=MAX_TOOL_EVIDENCE_IDS,
    )
    cached: bool = False
    replayed: bool = False

    @field_validator("evidence_ids")
    @classmethod
    def unique_evidence_ids(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("evidence_ids must be unique")
        return value

    @model_validator(mode="after")
    def valid_success_error_combination(self) -> ToolResult:
        if self.ok:
            if self.error_code is not None or self.error_category is not None:
                raise ValueError("successful results cannot contain error fields")
            if self.retryable:
                raise ValueError("successful results cannot be retryable")
            return self
        if self.error_code is None:
            raise ValueError("failed results require error_code")
        category = self.error_category or classify_error_code(self.error_code)
        self.error_category = category
        self.retryable = is_retryable(category)
        if self.message is None:
            self.message = error_message_for(self.error_code)
        return self
