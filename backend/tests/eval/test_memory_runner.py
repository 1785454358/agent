import json

import pytest

from deeptrace.eval.experiment import EvaluationLimits
from deeptrace.eval.memory_runner import load_episodes, main, run_memory_episode
from deeptrace.eval.scripted import ScriptedResearchModel


@pytest.mark.asyncio
async def test_cross_thread_recall_is_not_chat_history_and_gold_is_score_side():
    episode = next(e for e in load_episodes() if e.id == "preference-language")
    on = await run_memory_episode(
        episode,
        enabled=True,
        model_factory=ScriptedResearchModel,
        limits=EvaluationLimits(),
    )
    off = await run_memory_episode(
        episode,
        enabled=False,
        model_factory=ScriptedResearchModel,
        limits=EvaluationLimits(),
    )
    assert on["turns"][-1]["prior_messages"] == []
    assert on["turns"][-1]["target_hits"] == 1
    assert off["turns"][-1]["target_hits"] == 0
    assert on["memory_backend"] == "sqlite_lexical"
    assert on["violations"] == []
    assert on["turns"][-1]["checks"]["recalled_content_in_model_inputs"]
    assert off["turns"][-1]["checks"]["disabled_memory_empty"]
    assert off["cross_namespace_hits"] == 0
    prompts = json.dumps(on["turns"][-1]["trajectory"], ensure_ascii=False)
    assert "expected_contents" not in prompts
    assert "gold_canary_73d8" not in prompts
    assert "本轮用户明确要求优先于历史偏好" in prompts
    assert "请用英文" in prompts


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "episode_id",
    [
        "update-language",
        "forget-logical",
        "expiry-boundary",
        "expiry-after",
        "isolate-user",
        "isolate-workspace",
        "reuse-fact",
        "reuse-background",
    ],
)
async def test_sqlite_lifecycle_and_namespace_contracts(episode_id):
    episode = next(e for e in load_episodes() if e.id == episode_id)
    result = await run_memory_episode(
        episode,
        enabled=True,
        model_factory=ScriptedResearchModel,
        limits=EvaluationLimits(),
    )
    assert result["status"] == "completed"
    assert result["violations"] == []
    assert result["cross_namespace_hits"] == 0
    if episode_id == "update-language":
        versions = [r for r in result["stored_memories"] if r["type"] == "preference"]
        assert [(r["version"], r["status"]) for r in versions] == [
            (1, "superseded"),
            (2, "active"),
        ]
    if episode_id == "forget-logical":
        assert any(r["status"] == "deleted" for r in result["stored_memories"])
    if episode_id.startswith("expiry"):
        assert any(
            r["status"] == "expired" for r in result["turns"][-1]["stored_before"]
        )


@pytest.mark.asyncio
async def test_episode_model_budget_does_not_reset_between_turns():
    episode = next(e for e in load_episodes() if e.id == "reuse-fact")
    result = await run_memory_episode(
        episode,
        enabled=True,
        model_factory=ScriptedResearchModel,
        limits=EvaluationLimits(max_model_calls=8),
    )
    assert result["model_calls"] <= 8
    assert result["status"] == "partial"
    assert result["violations"]


def test_memory_cli_24_variants_and_exact_resume(tmp_path, monkeypatch):
    assert main(["--out", str(tmp_path)]) == 0
    first = (tmp_path / "memory_records.json").read_bytes()
    records = json.loads(first)
    assert len(records) == 24
    assert len({r["episode_id"] for r in records}) == 12
    assert all(r["data_kind"] == "controlled_scenario" for r in records)
    from deeptrace.eval import memory_runner

    monkeypatch.setattr(
        memory_runner,
        "run_memory_episode",
        lambda *a, **k: pytest.fail("resume must not execute"),
    )
    assert main(["--out", str(tmp_path), "--resume"]) == 0
    assert (tmp_path / "memory_records.json").read_bytes() == first


def test_episode_asset_rejects_unknown_and_oversized_inputs(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(
        json.dumps([{"id": "bad", "category": "bad", "stages": [], "surprise": True}]),
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        load_episodes(path)


@pytest.mark.asyncio
async def test_unavailable_write_is_not_a_successful_memory_enabled_episode(
    monkeypatch,
):
    from deeptrace.persistence.memory_store import SqlAlchemyMemoryStore

    async def unavailable(*a, **k):
        raise OSError("controlled_store_unavailable")

    monkeypatch.setattr(SqlAlchemyMemoryStore, "upsert", unavailable)
    episode = next(e for e in load_episodes() if e.id == "preference-language")
    result = await run_memory_episode(episode, enabled=True)
    assert result["status"] == "partial"
    assert "stage_0:application_partial" in result["violations"]


def test_cancelled_episode_remains_claimed_and_is_not_automatically_reissued(
    tmp_path, monkeypatch
):
    import asyncio

    from deeptrace.eval import memory_runner

    async def cancelled(*a, **k):
        raise asyncio.CancelledError

    monkeypatch.setattr(memory_runner, "run_memory_episode", cancelled)
    with pytest.raises(asyncio.CancelledError):
        main(["--out", str(tmp_path)])
    assert len(list((tmp_path / "claims").glob("*.json"))) == 1
    monkeypatch.setattr(
        memory_runner,
        "run_memory_episode",
        lambda *a, **k: pytest.fail("incomplete claim must not execute"),
    )
    with pytest.raises(SystemExit) as exc:
        main(["--out", str(tmp_path), "--resume"])
    assert exc.value.code == 2


@pytest.mark.asyncio
async def test_memory_runner_refuses_non_scripted_gateway_before_invocation():
    episode = load_episodes()[0]
    with pytest.raises(ValueError, match="scripted-only"):
        await run_memory_episode(episode, enabled=True, model_factory=object)
