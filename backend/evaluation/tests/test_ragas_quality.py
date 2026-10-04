"""Actual Ragas metrics with controlled external model responses; no network."""

import asyncio
import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ragas.llms.base import InstructorBaseRagasLLM
from ragas_quality import (
    AttemptLedger,
    cache_key,
    evaluate,
    score_metric,
    validate_export,
)


class ControlledLLM(InstructorBaseRagasLLM):
    def __init__(self, supported):
        self.supported = supported

    def generate(self, prompt, response_model):
        raise AssertionError("async only")

    async def agenerate(self, prompt, response_model):
        name = response_model.__name__
        if name == "StatementGeneratorOutput":
            return response_model(statements=["Checkpoint requires thread_id."])
        if name == "ClaimDecompositionOutput":
            return response_model(claims=["Checkpoint requires thread_id."])
        if name == "NLIStatementOutput":
            return response_model(
                statements=[
                    dict(
                        statement="Checkpoint requires thread_id.",
                        reason="controlled",
                        verdict=int(self.supported),
                    )
                ]
            )
        if name == "WorkflowOutput":
            return response_model(
                user_goal="Explain checkpoint", end_state="Explained checkpoint"
            )
        if name == "CompareOutcomeOutput":
            return response_model(reason="controlled", verdict=str(int(self.supported)))
        raise AssertionError(name)


def sample():
    return dict(
        record=dict(
            run_id="r",
            question="Explain checkpoint",
            answer="Checkpoint requires thread_id.",
            evidence=[
                dict(body="Checkpoint requires thread_id.", selected_for_outcome=True)
            ],
            artifact_errors=[],
        ),
        reference=dict(gold_answer="Checkpoint requires thread_id."),
    )


@pytest.mark.parametrize(
    "metric", ["faithfulness", "factual_correctness", "agent_goal_accuracy"]
)
def test_real_ragas_metrics_are_discriminative(metric):
    good = asyncio.run(score_metric(sample(), metric, ControlledLLM(True)))
    bad = asyncio.run(score_metric(sample(), metric, ControlledLLM(False)))
    assert good["status"] == bad["status"] == "ok"
    assert good["value"] > bad["value"]


def test_missing_context_is_not_zero():
    item = sample()
    item["record"]["evidence"] = []
    result = asyncio.run(score_metric(item, "faithfulness", ControlledLLM(True)))
    assert result["status"] == "not_applicable" and result["value"] is None


def test_cache_identity_covers_evidence_reference_and_judge():
    item = sample()
    original = cache_key(item, "faithfulness", {"model": "a"})
    for field in ("evidence", "reference", "judge"):
        changed = copy.deepcopy(item)
        judge = {"model": "a"}
        if field == "evidence":
            changed["record"]["evidence"][0]["body"] += " changed"
        elif field == "reference":
            changed["reference"]["gold_answer"] += " changed"
        else:
            judge["model"] = "b"
        assert cache_key(changed, "faithfulness", judge) != original


def test_attempt_budget_is_durable_and_no_retry_dispatch_over_limit(tmp_path):
    async def run():
        ledger = AttemptLedger(tmp_path / "attempts.json", 1)
        calls = []

        async def raw(**kwargs):
            calls.append(kwargs)
            raise RuntimeError("secret must not be stored")

        with pytest.raises(RuntimeError):
            await ledger.invoke(raw, model="a")
        restored = AttemptLedger(tmp_path / "attempts.json", 1)
        with pytest.raises(RuntimeError, match="budget"):
            await restored.invoke(raw, model="a")
        assert len(calls) == 1
        assert "secret" not in (tmp_path / "attempts.json").read_text()
        assert restored.snapshot()["input_tokens"] is None

    asyncio.run(run())


def test_cancelled_attempt_remains_consumed(tmp_path):
    async def run():
        ledger = AttemptLedger(tmp_path / "attempts.json", 2)

        async def raw(**kwargs):
            raise asyncio.CancelledError()

        with pytest.raises(asyncio.CancelledError):
            await ledger.invoke(raw)
        assert ledger.snapshot()["provider_attempts"] == 1

    asyncio.run(run())


def test_export_uses_production_canonical_manifest_hash():
    import hashlib
    import json

    manifest = {"model": {"name": "a"}, "schema_version": 2}
    item = sample()
    item["record"].update(question_id="q", status="completed", mode="baseline")
    item["reference"].update(id="q", question=item["record"]["question"])
    canonical = hashlib.sha256(
        json.dumps(
            manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()
    validate_export(
        dict(
            schema_version=2,
            identity_sha256=canonical,
            manifest=manifest,
            samples=[item],
        )
    )


@pytest.mark.parametrize("metric", ["factual_correctness", "agent_goal_accuracy"])
def test_large_unused_evidence_does_not_disable_reference_metrics(metric):
    item = sample()
    item["record"]["evidence"][0]["body"] += "x" * 100_001
    result = asyncio.run(score_metric(item, metric, ControlledLLM(True)))
    assert result == {"status": "ok", "value": 1.0, "reason": None}


def test_large_unused_gold_does_not_disable_faithfulness():
    item = sample()
    item["reference"]["gold_answer"] += "x" * 100_001
    result = asyncio.run(score_metric(item, "faithfulness", ControlledLLM(True)))
    assert result == {"status": "ok", "value": 1.0, "reason": None}


def test_large_used_evidence_is_not_silently_truncated():
    item = sample()
    item["record"]["evidence"][0]["body"] += "x" * 100_001
    result = asyncio.run(score_metric(item, "faithfulness", ControlledLLM(True)))
    assert result == {
        "status": "not_applicable",
        "value": None,
        "reason": "quality_input_size_limit",
    }


def test_actual_instructor_retries_are_metered_and_cached(tmp_path, monkeypatch):
    import openai
    from openai.types.chat import ChatCompletion

    calls = []
    original_client = openai.AsyncOpenAI

    class ControlledClient(original_client):
        def __init__(self, **kwargs):
            assert kwargs["max_retries"] == 0
            super().__init__(**kwargs)

            async def invalid_response(**request):
                calls.append(request)
                return ChatCompletion(
                    id="test",
                    object="chat.completion",
                    created=0,
                    model="test",
                    choices=[
                        dict(
                            index=0,
                            finish_reason="stop",
                            message=dict(role="assistant", content='{"invalid": true}'),
                        )
                    ],
                    usage=dict(prompt_tokens=10, completion_tokens=3, total_tokens=13),
                )

            self.chat.completions.create = invalid_response

    monkeypatch.setattr(openai, "AsyncOpenAI", ControlledClient)
    item = sample()
    item["record"].update(question_id="q", status="completed", mode="baseline")
    payload = dict(identity_sha256="experiment", samples=[item])
    credentials = dict(key="fake", url="https://example.com/v1")
    judge = dict(model="test")
    first = asyncio.run(evaluate(payload, tmp_path, judge, credentials, 2))
    assert len(calls) == first["usage"]["provider_attempts"] == 2
    assert first["usage"]["input_tokens"] == 20
    assert all(
        m["status"] == "error" and m["value"] is None
        for m in first["results"][0]["metrics"].values()
    )
    second = asyncio.run(evaluate(payload, tmp_path, judge, credentials, 2))
    assert len(calls) == 2
    assert second == first


def test_judge_records_bounded_prompt_and_result_not_sdk_metadata(tmp_path):
    import json
    from types import SimpleNamespace

    async def run():
        ledger = AttemptLedger(tmp_path / "attempts.json", 1)

        async def raw(**kwargs):
            return SimpleNamespace(
                usage=SimpleNamespace(prompt_tokens=2, completion_tokens=1),
                choices=[
                    SimpleNamespace(message=SimpleNamespace(content='{"verdict":"1"}'))
                ],
                secret_metadata="not_exported",
            )

        await ledger.invoke(
            raw,
            model="judge",
            messages=[{"role": "user", "content": "source evidence"}],
        )
        saved = json.loads((tmp_path / "attempts.json").read_text())
        assert saved[0]["messages"][0]["content"] == "source evidence"
        assert saved[0]["response"] == '{"verdict":"1"}'
        assert "not_exported" not in str(saved)

    asyncio.run(run())
