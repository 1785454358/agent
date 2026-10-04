"""Question-level paired analysis; failures and missing scores stay visible."""

from __future__ import annotations

import math
import random
from collections import Counter, defaultdict
from statistics import mean

METRICS = ("agent_goal_accuracy", "factual_correctness", "faithfulness")


def _quantile(values: list[float], probability: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    offset = (len(ordered) - 1) * probability
    lower = math.floor(offset)
    upper = math.ceil(offset)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (offset - lower)


def _paired_summary(baseline, candidate, values, *, completed_only, seed, resamples):
    differences, excluded = {}, []
    for question_id in sorted(baseline.keys() | candidate.keys()):
        left, right = baseline.get(question_id, []), candidate.get(question_id, [])
        left_indices = {r["repeat_index"] for r in left}
        right_indices = {r["repeat_index"] for r in right}
        runs = left + right
        eligible = bool(left and right and left_indices == right_indices)
        eligible = eligible and all(values.get(r["run_id"]) is not None for r in runs)
        if completed_only:
            eligible = eligible and all(r["status"] == "completed" for r in runs)
        if not eligible:
            excluded.append(question_id)
            continue
        differences[question_id] = mean(values[r["run_id"]] for r in right) - mean(
            values[r["run_id"]] for r in left
        )
    interval = None
    if len(differences) > 1:
        rng = random.Random(seed)
        deltas = list(differences.values())
        draws = [mean(rng.choices(deltas, k=len(deltas))) for _ in range(resamples)]
        interval = [_quantile(draws, 0.025), _quantile(draws, 0.975)]
    return {
        "paired_tasks": len(differences),
        "difference": mean(differences.values()) if differences else None,
        "interval_95": interval,
        "task_differences": differences,
        "excluded_tasks": excluded,
    }


def _system_summary(rows, values, metadata):
    by_question = defaultdict(list)
    for row in rows:
        by_question[row["question_id"]].append(row)
    quality = {}
    for metric in METRICS:
        available, categorical = {}, defaultdict(list)
        scored, errors, not_applicable, missing = 0, 0, 0, 0
        for question_id, repeats in by_question.items():
            scores = []
            for row in repeats:
                result = values.get(row["run_id"], {}).get(metric)
                if result is None:
                    missing += 1
                elif result["status"] == "ok":
                    scores.append(result["value"])
                    scored += 1
                elif result["status"] == "error":
                    errors += 1
                else:
                    not_applicable += 1
            if scores:
                available[question_id] = mean(scores)
                categorical[metadata[question_id]["category"]].append(mean(scores))
        quality[metric] = {
            "scored_runs": scored,
            "error_runs": errors,
            "not_applicable_runs": not_applicable,
            "missing_runs": missing,
            "coverage": scored / len(rows),
            "available_question_mean": mean(available.values()) if available else None,
            "question_means": available,
            "category_means": {c: mean(v) for c, v in sorted(categorical.items())},
        }
    tokens = {}
    for name in ("provider_attempts", "input_tokens", "output_tokens"):
        counts = [r.get("usage", {}).get(name) for r in rows]
        measured = [n for n in counts if type(n) is int and n >= 0]
        tokens[name] = {
            "total": sum(measured) if len(measured) == len(counts) else None,
            "observed_subtotal": sum(measured),
            "missing_runs": len(counts) - len(measured),
        }
    return {
        "attempted_tasks": len(by_question),
        "attempted_runs": len(rows),
        "completed_runs": sum(r["status"] == "completed" for r in rows),
        "answered_runs": sum(r["answered"] for r in rows),
        "status_counts": dict(Counter(r["status"] for r in rows)),
        "termination_counts": dict(Counter(r["termination_reason"] for r in rows)),
        "quality": quality,
        "usage": tokens,
        "latency_ms": {
            "p50": _quantile([r["wall_ms"] for r in rows], 0.5),
            "p95": _quantile([r["wall_ms"] for r in rows], 0.95),
        },
    }


def compare_records(records, score_rows, *, metadata, seed=0, resamples=2000):
    """Separate dataset/split/kind; aggregate repeats, then pair task differences.

    Primary quality pairs require matching repeat indices and fully measured
    scores for BOTH systems. Available-case system means are explicitly labeled.
    """
    if (
        type(seed) is not int
        or type(resamples) is not int
        or not 100 <= resamples <= 10_000
    ):
        raise ValueError("integer seed and 100..10000 resamples required")
    if not isinstance(metadata, dict):
        raise ValueError("metadata object required")
    rows = [
        r.model_dump(mode="json") if hasattr(r, "model_dump") else dict(r)
        for r in records
    ]
    if not rows or len(rows) > 10_000:
        raise ValueError("1..10000 records required")
    ids, repeats, groups = {}, set(), defaultdict(list)
    for row in rows:
        if any(
            not isinstance(row.get(k), str) or not row[k]
            for k in ("question_id", "run_id", "mode", "termination_reason")
        ):
            raise ValueError("nonempty record identifiers required")
        if not isinstance(row.get("usage", {}), dict):
            raise ValueError("usage object required; unknown counts may be null")
        qid, run_id = row["question_id"], row["run_id"]
        meta = metadata.get(qid)
        if not isinstance(meta, dict) or any(
            not isinstance(meta.get(k), str) or not meta[k]
            for k in ("dataset", "split", "data_kind", "category")
        ):
            raise ValueError("explicit dataset, split, data kind and category required")
        if type(row.get("repeat_index")) is not int or row["repeat_index"] < 0:
            raise ValueError("invalid repeat index")
        key = (qid, row["mode"], row["repeat_index"])
        if run_id in ids or key in repeats:
            raise ValueError("duplicate run or repeat")
        if (
            row["status"] not in {"completed", "partial", "failed"}
            or type(row["answered"]) is not bool
        ):
            raise ValueError("invalid run state")
        if (
            type(row["wall_ms"]) not in {int, float}
            or not math.isfinite(row["wall_ms"])
            or row["wall_ms"] < 0
        ):
            raise ValueError("invalid latency")
        ids[run_id] = row
        repeats.add(key)
        groups[(meta["dataset"], meta["split"], meta["data_kind"])].append(row)
    scores = {}
    for score in score_rows:
        if not isinstance(score, dict) or not isinstance(score.get("run_id"), str):
            raise ValueError("judge record object required")
        run_id = score["run_id"]
        if run_id not in ids or run_id in scores:
            raise ValueError("unknown or duplicate judge run")
        row = ids[run_id]
        if score["mode"] != row["mode"] or score["question_id"] != row["question_id"]:
            raise ValueError("judge identity mismatch")
        if not isinstance(score["metrics"], dict):
            raise ValueError("invalid judge metrics")
        for name, metric in score["metrics"].items():
            if (
                not isinstance(metric, dict)
                or name not in METRICS
                or metric.get("status") not in {"ok", "error", "not_applicable"}
            ):
                raise ValueError("unsupported metric contract")
            value = metric.get("value")
            if metric["status"] == "ok":
                if (
                    type(value) not in {int, float}
                    or not math.isfinite(value)
                    or not 0 <= value <= 1
                ):
                    raise ValueError("invalid measured metric")
            elif value is not None:
                raise ValueError("unmeasured metric must be null")
        scores[run_id] = score["metrics"]
    reports = []
    for (dataset, split, kind), subset in sorted(groups.items()):
        systems = defaultdict(list)
        by_system_question = defaultdict(lambda: defaultdict(list))
        for row in subset:
            systems[row["mode"]].append(row)
            by_system_question[row["mode"]][row["question_id"]].append(row)
        comparisons = {}
        for system in sorted(set(systems) - {"baseline"}):
            comparisons[system] = {}
            for metric in METRICS:
                values = {
                    r["run_id"]: scores.get(r["run_id"], {})
                    .get(metric, {})
                    .get("value")
                    for r in subset
                }
                comparisons[system][metric] = {
                    view: _paired_summary(
                        by_system_question["baseline"],
                        by_system_question[system],
                        values,
                        completed_only=view == "completed_only",
                        seed=seed,
                        resamples=resamples,
                    )
                    for view in ("all_output", "completed_only")
                }
        reports.append(
            {
                "dataset": dataset,
                "split": split,
                "data_kind": kind,
                "systems": {
                    s: _system_summary(r, scores, metadata)
                    for s, r in sorted(systems.items())
                },
                "comparisons": comparisons,
            }
        )
    return {
        "schema_version": 1,
        "method": "question_paired_percentile_bootstrap",
        "seed": seed,
        "resamples": resamples,
        "confidence_level": 0.95,
        "difference_direction": "candidate_minus_baseline",
        "groups": reports,
    }


def render_comparison(report: dict) -> str:
    lines = [
        "# Paired quality comparison",
        "",
        "System quality means below are available-case question means; "
        "consult JSON for coverage. Repeat scores are averaged within question. "
        "Missing metrics are not zero. "
        "Completed-only and all-output pairs are separate.",
        "",
    ]
    for group in report["groups"]:
        lines.extend(
            [
                f"## {group['dataset']} / {group['split']} / {group['data_kind']}",
                "",
                "| system | attempted runs | completed | "
                "goal | factual F1 | faithfulness |",
                "| --- | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for system, stats in group["systems"].items():
            numbers = [stats["quality"][m]["available_question_mean"] for m in METRICS]
            lines.append(
                f"| {system} | {stats['attempted_runs']} | {stats['completed_runs']} | "
                + " | ".join("N/A" if n is None else f"{n:.3f}" for n in numbers)
                + " |"
            )
        lines.append("")
        for system, metrics in group["comparisons"].items():
            for name, views in metrics.items():
                for view, stats in views.items():
                    lines.append(
                        f"- {system} vs baseline, {name}, {view}: "
                        f"n={stats['paired_tasks']}, delta={stats['difference']}, "
                        f"CI95={stats['interval_95']}; "
                        f"excluded={len(stats['excluded_tasks'])}"
                    )
        lines.append("")
    lines.append(
        "No population-effect or significance claim from a single pair; "
        "intervals for zero/one pair are null. "
        "Full coverage and exclusions are in comparison.json."
    )
    return "\n".join(lines)
