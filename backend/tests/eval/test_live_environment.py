import asyncio

import pytest
from deeptrace.eval.env import CorpusFetcher, CorpusSearch, build_eval_context
from deeptrace.eval.experiment import EvaluationLimits, ModelIdentity, build_manifest
from deeptrace.eval.scripted import ScriptedResearchModel
from tests.eval.test_env import _corpus
from tests.eval.test_experiment import assets


def test_explicit_live_adapters_cannot_silently_fall_back_to_corpus():
    corpus = _corpus()
    search, fetcher = CorpusSearch(corpus), CorpusFetcher(corpus)
    env = build_eval_context(
        None,
        model_gateway=ScriptedResearchModel(),
        run_id="live",
        search=search,
        fetcher=fetcher,
    )
    assert env.search is search and env.fetcher is fetcher
    assert env.context.clock.now().year >= 2026
    for kwargs in ({"search": search}, {"fetcher": fetcher}, {}):
        with pytest.raises(ValueError):
            build_eval_context(
                None, model_gateway=ScriptedResearchModel(), run_id="live", **kwargs
            )
    asyncio.run(env.aclose())


def test_live_identity_has_no_frozen_corpus_or_credentials():
    questions, _ = assets()
    manifest = build_manifest(
        questions,
        None,
        model=ModelIdentity(kind="real", name="test"),
        modes=["plan_execute"],
        repeats=1,
        run_prefix="live",
        limits=EvaluationLimits(),
        live_retrieval={"search": "tavily", "fetch": "AsyncWebFetcher"},
    )
    assert manifest["tools_backend"] == "live_web"
    assert manifest["corpus_sha256"] is None
    assert manifest["live_retrieval"]["search"] == "tavily"
    with pytest.raises(ValueError):
        build_manifest(
            questions,
            None,
            model=ModelIdentity(kind="real", name="test"),
            modes=["plan_execute"],
            repeats=1,
            run_prefix="live",
            limits=EvaluationLimits(),
        )


def test_live_cli_rejects_frozen_inputs_before_factories(tmp_path):
    from deeptrace.eval.live import main

    with pytest.raises(SystemExit) as exc:
        main(["--corpus", "not-used", "--out", str(tmp_path / "out")])
    assert exc.value.code == 2
    assert not (tmp_path / "out").exists()
