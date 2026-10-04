import json

import pytest
from pydantic import ValidationError

from deeptrace.eval import Corpus, CorpusDocument, EvalQuestion


def assets():
    return [EvalQuestion(id="q", question="checkpoint?", gold_answer="gold")], Corpus(
        [
            CorpusDocument(
                doc_id="d", url="https://example.org/d", title="d", body="facts"
            )
        ]
    )


def test_manifest_hashes_worktree_source_and_assets_without_gold_payload(tmp_path):
    from deeptrace.eval.experiment import (
        EvaluationLimits,
        ModelIdentity,
        build_manifest,
    )

    source = tmp_path / "backend/src/deeptrace/eval"
    source.mkdir(parents=True)
    (source / "runner.py").write_text("source version one", encoding="utf-8")
    (tmp_path / ".env").write_text("SECRET=never-export", encoding="utf-8")
    questions, corpus = assets()
    kwargs = dict(
        model=ModelIdentity(kind="scripted", name="scripted"),
        modes=["workflow"],
        repeats=1,
        run_prefix="run",
        limits=EvaluationLimits(),
        project_root=tmp_path,
    )
    first = build_manifest(questions, corpus, **kwargs)
    (source / "runner.py").write_text("source version two", encoding="utf-8")
    second = build_manifest(questions, corpus, **kwargs)
    assert first["source_files"] != second["source_files"]
    assert first["dataset_sha256"] == second["dataset_sha256"]
    assert first["schema_version"] == 2
    assert first["sample_ids"] == ["run-q-workflow"]
    assert first.get("research_context_policy") == {
        "soft_input_tokens": 6000,
        "recent_exchange_groups": 3,
        "retained_actual_read_previews": 3,
    }
    assert "never-export" not in json.dumps(first)
    assert '"gold"' not in json.dumps(first)


def test_provider_identity_strips_credentials_query_and_fragment():
    from deeptrace.eval.experiment import provider_origin

    assert (
        provider_origin("https://user:password@proxy.example:443/v1?key=secret#token")
        == "https://proxy.example:443"
    )
    with pytest.raises(ValueError):
        provider_origin("not a url")


def test_source_identity_pins_data_cards_and_licenses(tmp_path):
    from deeptrace.eval.experiment import source_identity

    data = tmp_path / "backend/src/deeptrace/eval/data"
    data.mkdir(parents=True)
    (data / "card.json").write_text('{"split":"dev"}')
    (data / "LICENSE.txt").write_text("MIT")
    (data / "source.mdx").write_text("public source")
    first = source_identity(tmp_path)
    (data / "card.json").write_text('{"split":"test"}')
    second = source_identity(tmp_path)
    assert first != second
    assert "backend/src/deeptrace/eval/data/LICENSE.txt" in first
    assert "backend/src/deeptrace/eval/data/source.mdx" in first


@pytest.mark.parametrize(
    "field",
    [
        "max_model_calls",
        "max_tool_calls",
        "max_provider_attempts",
        "run_timeout_seconds",
        "agent_iterations",
    ],
)
def test_limits_reject_zero_and_boolean(field):
    from deeptrace.eval.experiment import EvaluationLimits

    for invalid in (0, True):
        with pytest.raises(ValidationError):
            EvaluationLimits(**{field: invalid})


def test_model_identity_rejects_accidental_settings_or_key_fields():
    from deeptrace.eval.experiment import ModelIdentity

    with pytest.raises(ValidationError):
        ModelIdentity(kind="real", name="model", api_key="secret")


def test_manifest_rejects_duplicate_modes_before_any_run():
    from deeptrace.eval.experiment import (
        EvaluationLimits,
        ModelIdentity,
        build_manifest,
    )

    questions, corpus = assets()
    with pytest.raises(ValueError, match="unique"):
        build_manifest(
            questions,
            corpus,
            model=ModelIdentity(kind="scripted", name="x"),
            modes=["workflow", "workflow"],
            repeats=1,
            run_prefix="r",
            limits=EvaluationLimits(),
        )


def test_provider_route_changes_identity_without_exporting_url_credentials():
    from deeptrace.eval.experiment import provider_endpoint_hash

    assert provider_endpoint_hash("https://proxy.example/v1") != provider_endpoint_hash(
        "https://proxy.example/other/v1"
    )
    for url in (
        "https://u:password@proxy.example/v1",
        "https://proxy.example/v1?key=secret",
    ):
        with pytest.raises(ValueError, match="credential"):
            provider_endpoint_hash(url)
