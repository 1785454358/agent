import json

import pytest

from deeptrace.eval.__main__ import main


def test_benchmark_preflight_before_factory_and_output(tmp_path, monkeypatch):
    from deeptrace.eval import __main__ as cli
    from tests.eval.test_assets import bundle_fixture, save

    path, payload = bundle_fixture(tmp_path)
    payload["tasks"][0]["references"][0]["quote"] = "corrupted"
    save(path, payload)
    out = tmp_path / "run"
    monkeypatch.setattr(
        cli, "_model_factories", lambda *a, **k: pytest.fail("preflight first")
    )
    with pytest.raises(SystemExit) as exc:
        main(["--benchmark", str(path), "--out", str(out)])
    assert exc.value.code == 2
    assert not out.exists()


def test_benchmark_export_provenance_and_split_resume(tmp_path, monkeypatch):
    from deeptrace.eval import __main__ as cli
    from tests.eval.test_assets import bundle_fixture

    path, _ = bundle_fixture(tmp_path)
    out = tmp_path / "run"
    args = [
        "--benchmark",
        str(path),
        "--split",
        "dev",
        "--modes",
        "workflow",
        "--out",
        str(out),
    ]
    assert main(args) == 0
    export = json.loads((out / "quality_eval.json").read_text(encoding="utf-8"))
    assert export["manifest"]["benchmark"]["split"] == "dev"
    assert export["dataset_provenance"]["human_reviewed"] == 0
    assert len(export["samples"]) == 1
    assert "score_only_requirement" not in str(export["samples"][0]["record"])
    assert "gold_canary_14a" not in str(export["samples"][0]["record"])
    first = (out / "records.json").read_bytes()
    assert main([*args, "--resume"]) == 0
    assert first == (out / "records.json").read_bytes()
    monkeypatch.setattr(
        cli, "_model_factories", lambda *a, **k: pytest.fail("identity first")
    )
    changed = [
        "--benchmark",
        str(path),
        "--split",
        "test",
        "--modes",
        "workflow",
        "--out",
        str(out),
        "--resume",
    ]
    with pytest.raises(SystemExit) as exc:
        main(changed)
    assert exc.value.code == 2


@pytest.mark.parametrize(
    "flags",
    [
        ["--split", "test"],
        ["--benchmark", "missing", "--dataset", "missing"],
        ["--benchmark", "missing", "--corpus", "missing"],
    ],
)
def test_benchmark_does_not_silently_mix_legacy_inputs(tmp_path, monkeypatch, flags):
    from deeptrace.eval import __main__ as cli

    monkeypatch.setattr(
        cli, "_model_factories", lambda *a, **k: pytest.fail("preflight first")
    )
    with pytest.raises(SystemExit) as exc:
        main([*flags, "--out", str(tmp_path / "out")])
    assert exc.value.code == 2
    assert not (tmp_path / "out").exists()


def test_cli_durable_export_resume_and_v1_tool_compatibility(tmp_path):
    args = ["--modes", "workflow", "--out", str(tmp_path)]
    assert main(args) == 0
    assert (tmp_path / "manifest.json").exists()
    first = (tmp_path / "records.json").read_bytes()
    assert main([*args, "--resume"]) == 0
    assert (tmp_path / "records.json").read_bytes() == first
    quality = json.loads((tmp_path / "quality_eval.json").read_text(encoding="utf-8"))
    assert quality["schema_version"] == 2
    assert quality["samples"][0]["record"]["evidence"]
    tools = json.loads((tmp_path / "tool_eval.json").read_text(encoding="utf-8"))
    assert tools["schema_version"] == 1
    assert "model_messages" not in tools["samples"][0]["trajectory"]


def test_real_cli_rejects_missing_batch_budget_before_key_or_api_use(
    tmp_path, monkeypatch
):
    from deeptrace.eval import __main__ as cli

    def forbidden_factory(*args, **kwargs):
        raise AssertionError("budget preflight must precede model construction")

    monkeypatch.setattr(cli, "_model_factories", forbidden_factory)
    with pytest.raises(SystemExit) as exc:
        main(["--model", "real", "--out", str(tmp_path)])
    assert exc.value.code == 2
    assert list(tmp_path.iterdir()) == []


def test_resume_requires_output_directory():
    with pytest.raises(SystemExit) as exc:
        main(["--resume"])
    assert exc.value.code == 2


def test_resume_does_not_reset_consumed_batch_model_budget(tmp_path):
    args = [
        "--modes",
        "workflow",
        "--out",
        str(tmp_path),
        "--max-batch-model-calls",
        "1",
    ]
    assert main(args) == 1
    first = (tmp_path / "records.json").read_bytes()
    assert main([*args, "--resume"]) == 1
    assert (tmp_path / "records.json").read_bytes() == first


def test_real_legacy_judge_is_rejected_before_factory(tmp_path, monkeypatch):
    from deeptrace.eval import __main__ as cli

    monkeypatch.setattr(
        cli, "_model_factories", lambda *a, **k: pytest.fail("must preflight")
    )
    with pytest.raises(SystemExit) as exc:
        main(
            [
                "--model",
                "real",
                "--judge",
                "--out",
                str(tmp_path),
                "--max-batch-model-calls",
                "40",
                "--max-batch-provider-attempts",
                "80",
            ]
        )
    assert exc.value.code == 2


@pytest.mark.asyncio
async def test_offline_eval_http_guard_stops_dispatch():
    import httpx

    async with httpx.AsyncClient() as client:
        with pytest.raises(RuntimeError, match="offline_eval_network_blocked"):
            await client.get("https://example.org")


def test_cli_response_cap_is_identical_for_both_systems_and_in_manifest(tmp_path):
    assert (
        main(
            [
                "--modes",
                "workflow",
                "--include-baseline",
                "--response-max-chars",
                "600",
                "--out",
                str(tmp_path),
            ]
        )
        == 0
    )
    payload = json.loads((tmp_path / "quality_eval.json").read_text(encoding="utf-8"))
    assert payload["manifest"]["response_max_content_chars"] == 600
    assert {r["record"]["mode"] for r in payload["samples"]} == {"workflow", "baseline"}
    assert all(len(r["record"]["answer"]) <= 600 for r in payload["samples"])


@pytest.mark.parametrize("cap", ["0", "-1"])
def test_invalid_response_cap_fails_before_model_factory(tmp_path, monkeypatch, cap):
    from deeptrace.eval import __main__ as cli

    monkeypatch.setattr(
        cli, "_model_factories", lambda *a, **k: pytest.fail("must preflight")
    )
    with pytest.raises(SystemExit) as exc:
        main(["--response-max-chars", cap, "--out", str(tmp_path)])
    assert exc.value.code == 2
    assert not list(tmp_path.iterdir())


def test_changed_response_cap_cannot_resume_previous_experiment(tmp_path, monkeypatch):
    from deeptrace.eval import __main__ as cli

    assert (
        main(
            [
                "--modes",
                "workflow",
                "--response-max-chars",
                "600",
                "--out",
                str(tmp_path),
            ]
        )
        == 0
    )
    monkeypatch.setattr(
        cli, "_model_factories", lambda *a, **k: pytest.fail("identity before factory")
    )
    with pytest.raises(SystemExit) as exc:
        main(
            [
                "--modes",
                "workflow",
                "--response-max-chars",
                "700",
                "--out",
                str(tmp_path),
                "--resume",
            ]
        )
    assert exc.value.code == 2
