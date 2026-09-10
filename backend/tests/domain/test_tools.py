import json

import pytest
from pydantic import ValidationError

from deeptrace.domain.tools import (
    MAX_TOOL_ARGUMENTS_BYTES,
    MAX_TOOL_PREVIEW_LENGTH,
    ToolName,
    ToolRequest,
    ToolResult,
)


_IDS = {
    "request_id": "request-1",
    "run_id": "run-1",
    "thread_id": "thread-1",
    "call_id": "call-1",
}


def test_tool_name_contains_only_atomic_research_tools() -> None:
    assert {member.value for member in ToolName} == {
        "search_web",
        "fetch_page",
        "search_memory",
    }


def test_tool_request_requires_bounded_correlation_ids() -> None:
    request = ToolRequest(
        **_IDS,
        tool=ToolName.SEARCH_WEB,
        arguments={"query": "LangGraph Harness", "options": {"limit": 3}},
    )

    assert request.tool is ToolName.SEARCH_WEB
    assert request.arguments["options"] == {"limit": 3}

    for field_name in _IDS:
        payload = {**_IDS, field_name: ""}
        with pytest.raises(ValidationError):
            ToolRequest(
                **payload,
                tool=ToolName.SEARCH_WEB,
                arguments={},
            )

        payload[field_name] = "x" * 129
        with pytest.raises(ValidationError):
            ToolRequest(
                **payload,
                tool=ToolName.SEARCH_WEB,
                arguments={},
            )


def test_tool_request_arguments_are_json_compatible_and_size_bounded() -> None:
    with pytest.raises(ValidationError):
        ToolRequest(
            **_IDS,
            tool=ToolName.SEARCH_WEB,
            arguments={"client": object()},
        )

    oversized = {"value": "x" * MAX_TOOL_ARGUMENTS_BYTES}
    assert len(json.dumps(oversized).encode("utf-8")) > MAX_TOOL_ARGUMENTS_BYTES
    with pytest.raises(ValidationError, match="arguments exceed"):
        ToolRequest(
            **_IDS,
            tool=ToolName.SEARCH_WEB,
            arguments=oversized,
        )


def test_tool_result_represents_bounded_success_without_full_content() -> None:
    result = ToolResult(
        **_IDS,
        tool=ToolName.FETCH_PAGE,
        ok=True,
        preview="bounded summary",
        data_ref="evidence://evidence-1/body",
        evidence_ids=["evidence-1", "evidence-2"],
        cached=True,
        replayed=False,
    )

    assert result.error_code is None
    assert result.cached is True
    assert result.model_dump()["preview"] == "bounded summary"
    assert "content" not in ToolResult.model_fields
    assert "body" not in ToolResult.model_fields

    with pytest.raises(ValidationError):
        ToolResult(
            **_IDS,
            tool=ToolName.FETCH_PAGE,
            ok=True,
            preview="bounded",
            content="must live in the evidence store",
        )

    with pytest.raises(ValidationError):
        ToolResult(
            **_IDS,
            tool=ToolName.FETCH_PAGE,
            ok=True,
            preview="x" * (MAX_TOOL_PREVIEW_LENGTH + 1),
        )


@pytest.mark.parametrize(
    ("ok", "error_code"),
    [(True, "provider_timeout"), (False, None)],
)
def test_tool_result_rejects_invalid_success_error_combinations(
    ok: bool,
    error_code: str | None,
) -> None:
    with pytest.raises(ValidationError):
        ToolResult(
            **_IDS,
            tool=ToolName.SEARCH_WEB,
            ok=ok,
            error_code=error_code,
            preview="",
        )


def test_tool_result_rejects_duplicate_evidence_ids() -> None:
    with pytest.raises(ValidationError, match="evidence_ids must be unique"):
        ToolResult(
            **_IDS,
            tool=ToolName.SEARCH_MEMORY,
            ok=True,
            preview="result",
            evidence_ids=["evidence-1", "evidence-1"],
        )


def test_tool_result_rejects_whitespace_only_data_ref() -> None:
    with pytest.raises(ValidationError):
        ToolResult(
            **_IDS,
            tool=ToolName.FETCH_PAGE,
            ok=True,
            preview="result",
            data_ref=" \t ",
        )
