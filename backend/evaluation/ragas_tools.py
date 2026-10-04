"""Offline Ragas scorer. Run in .venv-ragas; never import the production app."""

from __future__ import annotations

import argparse
import asyncio
import copy
import hashlib
import json
import math
import os
import sys
import warnings
from collections import defaultdict
from importlib.metadata import version
from pathlib import Path

METRICS = ("tool_call_accuracy", "tool_call_f1")


def _load_framework():
    # Disable analytics before importing any framework code, even if inherited false.
    os.environ["RAGAS_DO_NOT_TRACK"] = "true"
    os.environ["LANGSMITH_TRACING"] = "false"
    try:
        from ragas.messages import AIMessage, HumanMessage, ToolCall
        from ragas.metrics.collections import ToolCallAccuracy, ToolCallF1
    except ImportError as exc:
        raise RuntimeError(
            "Ragas is unavailable; run this command with .venv-ragas"
        ) from exc
    framework_version = version("ragas")
    if framework_version != "0.4.3":
        raise RuntimeError(
            "Unsupported Ragas version; install evaluation/requirements.lock"
        )
    return AIMessage, HumanMessage, ToolCall, ToolCallAccuracy, ToolCallF1


def _unmeasured(status, reason):
    return {
        "status": status,
        "value": None,
        "reason": reason,
        "error": reason if status == "error" else None,
    }


async def score_export(payload: dict) -> dict:
    if type(payload.get("schema_version")) is not int or payload["schema_version"] != 1:
        raise ValueError("unsupported schema_version")
    if not isinstance(payload.get("samples"), list) or not payload["samples"]:
        raise ValueError("samples must be a nonempty list")
    AIMessage, HumanMessage, ToolCall, ToolCallAccuracy, ToolCallF1 = _load_framework()
    results = []
    for sample in payload["samples"]:
        if not isinstance(sample, dict):
            raise TypeError("sample must be an object")
        if sample.get("status") not in {"completed", "partial", "failed"}:
            raise ValueError("invalid status")
        if sample.get("mode") not in {
            "workflow",
            "plan_execute",
            "multi_agent",
            "baseline",
        }:
            raise ValueError("invalid mode")
        if type(sample.get("strict_tool_order", False)) is not bool:
            raise ValueError("strict_tool_order must be boolean")
        reference_calls = sample.get("reference_tool_calls")
        if reference_calls is not None and not isinstance(reference_calls, list):
            raise ValueError("reference_tool_calls must be a list or null")
        trajectory = sample.get("trajectory")
        if trajectory is not None and not isinstance(trajectory, dict):
            raise ValueError("trajectory must be an object or null")
        turns = (
            trajectory.get("model_turns", []) if isinstance(trajectory, dict) else []
        )
        if not isinstance(turns, list) or any(
            not isinstance(turn, dict)
            or not isinstance(turn.get("tool_calls", []), list)
            for turn in turns
        ):
            raise ValueError("model_turns must contain objects with tool_calls lists")
        calls = [call for turn in turns for call in turn.get("tool_calls", [])]
        if any(not isinstance(call, dict) for call in calls):
            raise ValueError("tool_calls must contain objects")
        if reference_calls is not None and any(
            not isinstance(call, dict) for call in reference_calls
        ):
            raise ValueError("reference_tool_calls must contain objects")
        excluded = sum(call.get("name") == "write_todos" for call in calls)
        invalid = any(turn.get("invalid_tool_calls") for turn in turns)
        branches = {
            turn["branch"]
            for turn in turns
            if turn.get("tool_calls") and turn.get("role") == "researcher"
        }
        row = {
            "question_id": sample["question_id"],
            "mode": sample["mode"],
            "run_id": sample["run_id"],
            "system_status": sample["status"],
            "excluded_internal_calls": excluded,
            "excluded_reference_calls": sum(
                call.get("name") == "write_todos" for call in reference_calls or []
            ),
            "requested_calls": len(calls) - excluded,
            "executions": copy.deepcopy(trajectory.get("tool_executions", []))
            if isinstance(trajectory, dict)
            else [],
            "observations": copy.deepcopy(trajectory.get("tool_observations", []))
            if isinstance(trajectory, dict)
            else [],
            "metrics": {},
        }
        for name in METRICS:
            if sample.get("reference_tool_calls") is None:
                row["metrics"][name] = _unmeasured(
                    "not_applicable", "missing_reference"
                )
                continue
            if not isinstance(trajectory, dict) or "model_turns" not in trajectory:
                row["metrics"][name] = _unmeasured(
                    "not_applicable", "missing_trajectory"
                )
                continue
            if invalid:
                row["metrics"][name] = _unmeasured("error", "invalid_tool_request")
                continue
            if (
                name == "tool_call_accuracy"
                and sample.get("strict_tool_order", False)
                and len(branches) > 1
            ):
                row["metrics"][name] = _unmeasured(
                    "not_applicable", "parallel_strict_order_unsupported"
                )
                continue
            try:
                references = [
                    ToolCall(name=call["name"], args=call["args"])
                    for call in sample["reference_tool_calls"]
                    if call["name"] != "write_todos"
                ]
                messages = [HumanMessage(content=sample["question"])]
                for turn in turns:
                    tool_calls = [
                        ToolCall(name=call["name"], args=call["args"])
                        for call in turn.get("tool_calls", [])
                        if call["name"] != "write_todos"
                    ]
                    if tool_calls:
                        messages.append(AIMessage(content="", tool_calls=tool_calls))
                metric = (
                    ToolCallAccuracy(
                        strict_order=sample.get("strict_tool_order", False)
                    )
                    if name == "tool_call_accuracy"
                    else ToolCallF1()
                )
                with warnings.catch_warnings(record=True) as notices:
                    warnings.simplefilter("always")
                    result = await metric.ascore(
                        user_input=messages, reference_tool_calls=references
                    )
                value = float(result.value)
                if not math.isfinite(value) or not 0 <= value <= 1:
                    raise ValueError("invalid metric value")
                row["metrics"][name] = {
                    "status": "ok",
                    "value": value,
                    "reason": result.reason,
                    "error": None,
                    "warnings": [notice.category.__name__ for notice in notices],
                }
            except Exception as exc:  # noqa: BLE001 - per-metric error records preserve coverage.
                row["metrics"][name] = _unmeasured("error", type(exc).__name__)
        results.append(row)
    grouped = defaultdict(list)
    for row in results:
        grouped[row["mode"]].append(row)
    summary = {}
    for mode, rows in sorted(grouped.items()):
        metrics = {}
        for name in METRICS:
            scores = [row["metrics"][name] for row in rows]
            values = [score["value"] for score in scores if score["status"] == "ok"]
            metrics[name] = {
                "scored": len(values),
                "failed": sum(score["status"] == "error" for score in scores),
                "not_applicable": sum(
                    score["status"] == "not_applicable" for score in scores
                ),
                "coverage": len(values) / len(rows),
                "mean": sum(values) / len(values) if values else None,
            }
        summary[mode] = {
            "runs": len(rows),
            "system_failed_runs": sum(
                row["system_status"] != "completed" for row in rows
            ),
            "metrics": metrics,
        }
    return {
        "schema_version": 1,
        "framework": {"name": "ragas", "version": "0.4.3"},
        "provenance": copy.deepcopy(payload.get("provenance", {})),
        "input_sha256": hashlib.sha256(
            json.dumps(
                payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
            ).encode()
        ).hexdigest(),
        "scope": "requested tools; exclude write_todos only; no LLM judge",
        "results": results,
        "summary": summary,
    }


def render_report(report: dict) -> str:
    lines = [
        "# Ragas requested-tool evaluation (0–1)",
        "",
        f"Framework: ragas {report['framework']['version']}",
        "",
        "| mode | metric | scored | failed | not applicable | coverage | mean |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for mode, group in report["summary"].items():
        for name, metric in group["metrics"].items():
            mean = "N/A" if metric["mean"] is None else f"{metric['mean']:.4f}"
            lines.append(
                f"| {mode} | {name} | {metric['scored']} | {metric['failed']} | {metric['not_applicable']} | {metric['coverage']:.1%} | {mean} |"
            )
        lines.extend(
            [
                "",
                f"{mode}: system non-completed runs={group['system_failed_runs']} / {group['runs']}",
            ]
        )
    lines.extend(
        [
            "",
            "Scores measure requested names/arguments, not execution success or answer quality. Internal write_todos calls are excluded and counted. Unknown tools are retained. F1 is set-based: duplicate requests can retain F1=1 while increasing calls or reducing accuracy. Strict cross-branch order is not applicable. Missing/failed scores are null, not zero.",
        ]
    )
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    try:
        path = Path(args.input)
        if path.stat().st_size > 10 * 1024 * 1024:
            raise ValueError("input exceeds 10 MiB")
        report = asyncio.run(score_export(json.loads(path.read_text(encoding="utf-8"))))
    except (OSError, ValueError, TypeError, KeyError, RuntimeError) as exc:
        # Import failures have a fixed actionable message; never print input data.
        message = str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__
        print(f"Evaluation failed: {message}", file=sys.stderr)
        return 2
    output = Path(args.out)
    output.mkdir(parents=True, exist_ok=True)
    (output / "tool_scores.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output / "tool_report.md").write_text(render_report(report), encoding="utf-8")
    print(render_report(report))
    return int(
        any(
            metric["status"] == "error"
            for row in report["results"]
            for metric in row["metrics"].values()
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
