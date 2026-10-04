import asyncio
import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

SEARCH = {"name": "search_web", "args": {"query": "checkpoint"}}
FETCH = {"name": "fetch_page", "args": {"url": "https://example.com/a"}}


def sample(calls, *, references=None, strict=False):
    return {
        "schema_version": 1,
        "provenance": {"model_kind": "scripted"},
        "samples": [
            {
                "question_id": "q",
                "mode": "workflow",
                "run_id": "r",
                "status": "completed",
                "question": "Explain checkpoint",
                "strict_tool_order": strict,
                "reference_tool_calls": [SEARCH, FETCH]
                if references is None
                else references,
                "trajectory": {
                    "model_turns": [
                        {
                            "role": "researcher",
                            "branch": "checkpoint",
                            "tool_calls": calls,
                            "invalid_tool_calls": [],
                        }
                    ],
                    "tool_executions": [],
                },
            }
        ],
    }


@pytest.mark.parametrize(
    "calls,strict,accuracy,f1",
    [
        ([SEARCH, FETCH], False, 1.0, 1.0),
        ([{"name": "search_web", "args": {"query": "wrong"}}, FETCH], False, 0.5, 0.5),
        ([SEARCH], False, 0.0, 0.6667),
        ([SEARCH, FETCH, {"name": "unknown_tool", "args": {}}], False, 0.0, 0.8),
        ([FETCH, SEARCH], False, 1.0, 1.0),
        ([FETCH, SEARCH], True, 0.0, 1.0),
    ],
)
def test_adapter_scores_real_framework_with_distinguishable_cases(
    calls, strict, accuracy, f1
):
    from ragas_tools import score_export

    report = asyncio.run(score_export(sample(calls, strict=strict)))
    metrics = report["results"][0]["metrics"]
    assert report["framework"]["name"] == "ragas"
    assert report["framework"]["version"] == "0.4.3"
    assert metrics["tool_call_accuracy"]["value"] == accuracy
    assert metrics["tool_call_f1"]["value"] == f1


def test_missing_reference_is_not_scored_as_zero():
    from ragas_tools import render_report, score_export

    payload = sample([SEARCH])
    payload["samples"][0]["reference_tool_calls"] = None
    report = asyncio.run(score_export(payload))
    assert report["results"][0]["metrics"]["tool_call_f1"]["value"] is None
    assert report["results"][0]["metrics"]["tool_call_f1"]["status"] == "not_applicable"
    assert "N/A" in render_report(report)


def test_parallel_branches_are_order_independent_but_strict_is_unmeasured():
    from ragas_tools import score_export

    payload = sample([])
    turns = [
        {"role": "researcher", "branch": "a", "tool_calls": [SEARCH]},
        {"role": "researcher", "branch": "b", "tool_calls": [FETCH]},
    ]
    payload["samples"][0]["trajectory"]["model_turns"] = turns
    normal = asyncio.run(score_export(payload))
    payload["samples"][0]["trajectory"]["model_turns"] = turns[::-1]
    reordered = asyncio.run(score_export(payload))
    assert normal["results"][0]["metrics"] == reordered["results"][0]["metrics"]
    payload["samples"][0]["strict_tool_order"] = True
    strict = asyncio.run(score_export(payload))
    assert (
        strict["results"][0]["metrics"]["tool_call_accuracy"]["status"]
        == "not_applicable"
    )


def test_internal_planning_is_explicitly_excluded_and_failures_are_preserved():
    from ragas_tools import score_export

    payload = sample(
        [{"name": "write_todos", "args": {"todos": []}}, SEARCH, FETCH, FETCH]
    )
    payload["samples"][0]["status"] = "partial"
    execution = {
        "caller_id": "a",
        "request_id": "r",
        "call_id": "c",
        "tool": "fetch_page",
        "arguments": FETCH["args"],
        "ok": False,
        "error_code": "url_not_discovered",
    }
    payload["samples"][0]["trajectory"]["tool_executions"] = [execution]
    original = copy.deepcopy(payload)
    report = asyncio.run(score_export(payload))
    row = report["results"][0]
    assert row["excluded_internal_calls"] == 1
    assert row["requested_calls"] == 3
    assert row["executions"] == [execution]
    assert row["metrics"]["tool_call_f1"]["value"] == 1.0
    assert row["metrics"]["tool_call_accuracy"]["value"] == 0.0
    assert report["summary"]["workflow"]["system_failed_runs"] == 1
    assert payload == original


def test_malformed_requests_are_errors_not_zero_or_omitted():
    from ragas_tools import score_export

    payload = sample([SEARCH])
    payload["samples"][0]["trajectory"]["model_turns"][0]["invalid_tool_calls"] = [
        {"name": "fetch_page", "args": "bad JSON"}
    ]
    report = asyncio.run(score_export(payload))
    metric = report["results"][0]["metrics"]["tool_call_f1"]
    assert metric["value"] is None
    assert metric["status"] == "error"
    assert metric["error"] == "invalid_tool_request"
    assert report["summary"]["workflow"]["metrics"]["tool_call_f1"]["failed"] == 1


def test_cli_writes_report_without_any_project_import(tmp_path):
    from ragas_tools import main

    input_path = tmp_path / "input.json"
    input_path.write_text(json.dumps(sample([SEARCH, FETCH])), encoding="utf-8")
    assert main(["--input", str(input_path), "--out", str(tmp_path / "scores")]) == 0
    report = json.loads(
        (tmp_path / "scores" / "tool_scores.json").read_text(encoding="utf-8")
    )
    assert report["results"][0]["metrics"]["tool_call_f1"]["value"] == 1.0
    assert not any(
        name == "deeptrace" or name.startswith("deeptrace.") for name in sys.modules
    )


def test_unsupported_schema_fails_instead_of_reinterpreting_data():
    from ragas_tools import score_export

    payload = sample([])
    payload["schema_version"] = 2
    with pytest.raises(ValueError, match="schema_version"):
        asyncio.run(score_export(payload))


def test_scoring_never_opens_a_network_connection(monkeypatch):
    import socket

    from ragas_tools import score_export

    def forbidden(*args, **kwargs):
        raise AssertionError("network must not be used")

    async def score_without_network():
        # Windows asyncio needs a local socketpair to construct its event loop.
        # Guard only after loop setup so the assertion tests the scorer, not asyncio.
        monkeypatch.setattr(socket.socket, "connect", forbidden)
        return await score_export(sample([SEARCH, FETCH]))

    report = asyncio.run(score_without_network())
    assert report["results"][0]["metrics"]["tool_call_f1"]["value"] == 1.0


def test_empty_expected_calls_are_distinct_from_missing_annotations():
    from ragas_tools import score_export

    report = asyncio.run(score_export(sample([], references=[])))
    metrics = report["results"][0]["metrics"]
    # Ragas 0.4.3 itself differs on the empty-set case; never fabricate agreement.
    assert metrics["tool_call_accuracy"]["value"] == 1.0
    assert metrics["tool_call_f1"]["value"] == 0.0


def test_internal_tool_scope_is_applied_to_both_predictions_and_references():
    from ragas_tools import score_export

    planning = {"name": "write_todos", "args": {"todos": []}}
    payload = sample([planning, SEARCH, FETCH], references=[planning, SEARCH, FETCH])
    report = asyncio.run(score_export(payload))
    row = report["results"][0]
    assert row["excluded_reference_calls"] == 1
    assert row["metrics"]["tool_call_accuracy"]["value"] == 1.0
    assert row["metrics"]["tool_call_f1"]["value"] == 1.0


@pytest.mark.parametrize(
    "field,value",
    [
        ("strict_tool_order", "false"),
        ("status", "unknown"),
        ("reference_tool_calls", "not a list"),
    ],
)
def test_invalid_envelope_fields_are_rejected_not_coerced(field, value):
    from ragas_tools import score_export

    payload = sample([SEARCH])
    payload["samples"][0][field] = value
    with pytest.raises(ValueError, match=field):
        asyncio.run(score_export(payload))
