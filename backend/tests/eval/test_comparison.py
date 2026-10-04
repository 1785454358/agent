"""Catch pseudoreplication, score imputation and cross-dataset pairing."""

import pytest

from deeptrace.eval import comparison


def record(q, mode, repeat=0, status="completed"):
    return dict(
        question_id=q,
        mode=mode,
        repeat_index=repeat,
        run_id=f"{q}-{mode}-{repeat}",
        status=status,
        answered=status == "completed",
        termination_reason="completed" if status == "completed" else "execution_error",
        wall_ms=100,
        usage={},
    )


def score(row, value):
    return dict(
        run_id=row["run_id"],
        mode=row["mode"],
        question_id=row["question_id"],
        metrics={
            "factual_correctness": dict(status="ok", value=value)
            if value is not None
            else dict(status="error", value=None)
        },
    )


def metadata(*ids):
    return {
        q: dict(
            dataset="real", split="test", data_kind="real_source", category="memory"
        )
        for q in ids
    }


def test_question_means_precede_pairing_instead_of_weighting_repeats():
    rows = (
        [record("a", "baseline", i) for i in range(2)]
        + [record("a", "workflow", i) for i in range(2)]
        + [record("b", "baseline"), record("b", "workflow")]
    )
    scores = [score(r, v) for r, v in zip(rows, [0, 0, 0, 1, 0, 1], strict=True)]
    report = comparison.compare_records(
        rows, scores, metadata=metadata("a", "b"), seed=7
    )
    pair = report["groups"][0]["comparisons"]["workflow"]["factual_correctness"][
        "all_output"
    ]
    assert pair["paired_tasks"] == 2
    assert pair["difference"] == 0.75  # (0.5 + 1)/2, NOT (0+1+1)/3
    assert pair["interval_95"] == [0.5, 1.0]


def test_missing_repeat_excludes_primary_pair_without_imputing_zero():
    rows = [record("a", m, i) for m in ("baseline", "workflow") for i in range(2)]
    report = comparison.compare_records(
        rows,
        [score(r, v) for r, v in zip(rows, [0, 0, 1, None], strict=True)],
        metadata=metadata("a"),
    )
    group = report["groups"][0]
    pair = group["comparisons"]["workflow"]["factual_correctness"]["all_output"]
    assert pair["paired_tasks"] == 0
    assert pair["difference"] is None
    assert pair["excluded_tasks"] == ["a"]
    system = group["systems"]["workflow"]
    assert system["quality"]["factual_correctness"]["coverage"] == 0.5
    assert system["quality"]["factual_correctness"]["available_question_mean"] == 1.0


def test_failure_remains_in_denominator_and_completed_pair_is_separate():
    rows = [record("a", "baseline", status="partial"), record("a", "workflow")]
    group = comparison.compare_records(
        rows, [score(rows[0], 0), score(rows[1], 0.5)], metadata=metadata("a")
    )["groups"][0]
    assert group["systems"]["baseline"]["attempted_runs"] == 1
    assert group["systems"]["baseline"]["completed_runs"] == 0
    metric = group["comparisons"]["workflow"]["factual_correctness"]
    assert metric["all_output"]["difference"] == 0.5
    assert metric["all_output"]["interval_95"] is None
    assert metric["completed_only"]["paired_tasks"] == 0


def test_zero_coverage_is_unknown_not_zero_quality():
    rows = [record("a", "baseline"), record("a", "workflow")]
    group = comparison.compare_records(rows, [], metadata=metadata("a"))["groups"][0]
    assert group["systems"]["workflow"]["quality"]["faithfulness"]["coverage"] == 0
    assert (
        group["systems"]["workflow"]["quality"]["faithfulness"][
            "available_question_mean"
        ]
        is None
    )


def test_dataset_split_and_kind_are_never_mixed():
    rows = [record(q, m) for q in ("a", "b", "c") for m in ("baseline", "workflow")]
    meta = metadata("a", "b", "c")
    meta["b"]["split"] = "dev"
    meta["c"]["data_kind"] = "synthetic"
    assert len(comparison.compare_records(rows, [], metadata=meta)["groups"]) == 3


def test_repeat_indices_must_match_for_primary_pair():
    rows = [record("a", "baseline", 0), record("a", "workflow", 1)]
    group = comparison.compare_records(
        rows, [score(r, 1) for r in rows], metadata=metadata("a")
    )["groups"][0]
    assert (
        group["comparisons"]["workflow"]["factual_correctness"]["all_output"][
            "paired_tasks"
        ]
        == 0
    )


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -0.1, 1.1, True])
def test_invalid_metric_values_reject_report(bad):
    row = record("a", "workflow")
    with pytest.raises(ValueError):
        comparison.compare_records([row], [score(row, bad)], metadata=metadata("a"))


def test_duplicates_and_foreign_judge_rows_are_rejected():
    row = record("a", "workflow")
    with pytest.raises(ValueError):
        comparison.compare_records([row, row], [], metadata=metadata("a"))
    with pytest.raises(ValueError):
        comparison.compare_records(
            [row], [score(record("b", "workflow"), 1)], metadata=metadata("a")
        )


def test_seeded_bootstrap_is_reproducible():
    rows = [record(q, m) for q in ("a", "b", "c") for m in ("baseline", "workflow")]
    scores = [score(r, v) for r, v in zip(rows, [0, 0.2, 0, 0.5, 0, 1], strict=True)]
    first = comparison.compare_records(
        rows, scores, metadata=metadata("a", "b", "c"), seed=4
    )
    assert first == comparison.compare_records(
        rows, scores, metadata=metadata("a", "b", "c"), seed=4
    )


def test_analysis_cli_refuses_mismatched_judge_before_creating_output(tmp_path):
    import json

    from deeptrace.eval.compare_cli import main
    from deeptrace.eval.trajectory import _content_hash

    manifest = {"dataset_sha256": "d", "corpus_sha256": "c"}
    row = record("a", "baseline")
    payload = dict(
        schema_version=2,
        manifest=manifest,
        identity_sha256=_content_hash(manifest),
        samples=[dict(record=row)],
    )
    inputs = [
        payload,
        dict(experiment_identity="other", results=[score(row, 0)]),
        dict(dataset_sha256="d", corpus_sha256="c", questions=metadata("a")),
    ]
    paths = []
    for index, item in enumerate(inputs):
        path = tmp_path / f"input{index}.json"
        path.write_text(json.dumps(item))
        paths.append(str(path))
    out = tmp_path / "analysis"
    with pytest.raises(SystemExit) as exc:
        main(
            [
                "--input",
                paths[0],
                "--scores",
                paths[1],
                "--metadata",
                paths[2],
                "--out",
                str(out),
            ]
        )
    assert exc.value.code == 2
    assert not out.exists()


def test_malformed_metric_object_is_validation_error():
    row = record("a", "workflow")
    item = score(row, 1)
    item["metrics"]["factual_correctness"] = "not a metric object"
    with pytest.raises(ValueError):
        comparison.compare_records([row], [item], metadata=metadata("a"))


@pytest.mark.parametrize(
    "field,bad", [("mode", None), ("question_id", 7), ("run_id", ""), ("usage", None)]
)
def test_malformed_record_boundary_is_validation_error(field, bad):
    row = record("a", "workflow")
    row[field] = bad
    with pytest.raises(ValueError):
        comparison.compare_records([row], [], metadata=metadata("a"))


def test_analysis_cli_requires_exact_judged_input_not_only_manifest(tmp_path):
    import json

    from deeptrace.eval.compare_cli import main
    from deeptrace.eval.trajectory import _content_hash

    manifest = {"dataset_sha256": "d", "corpus_sha256": "c"}
    row = record("a", "baseline")
    payload = dict(
        schema_version=2,
        manifest=manifest,
        identity_sha256=_content_hash(manifest),
        samples=[dict(record=row)],
    )
    scores = dict(
        experiment_identity=payload["identity_sha256"],
        judge={"model": "scripted"},
        results=[score(row, 0)],
    )
    identity = dict(input_sha256="different-input", judge=scores["judge"])
    inputs = {
        "quality_eval.json": payload,
        "quality_scores.json": scores,
        "identity.json": identity,
        "metadata.json": dict(
            dataset_sha256="d", corpus_sha256="c", questions=metadata("a")
        ),
    }
    for name, value in inputs.items():
        (tmp_path / name).write_text(json.dumps(value), encoding="utf-8")
    out = tmp_path / "analysis"
    args = [
        "--input",
        str(tmp_path / "quality_eval.json"),
        "--scores",
        str(tmp_path / "quality_scores.json"),
        "--metadata",
        str(tmp_path / "metadata.json"),
        "--out",
        str(out),
    ]
    with pytest.raises(SystemExit) as exc:
        main(args)
    assert exc.value.code == 2
    assert not out.exists()
    identity["input_sha256"] = _content_hash(payload)
    (tmp_path / "identity.json").write_text(json.dumps(identity), encoding="utf-8")
    assert main(args) == 0
    assert (out / "comparison.json").exists()
