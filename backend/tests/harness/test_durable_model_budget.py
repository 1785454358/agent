import asyncio
import copy

import pytest
from langchain_core.messages import AIMessage

from deeptrace.harness.model_budget import RunBudgetModelGateway
from deeptrace.harness.prompts import task_messages


class SnapshotStore:
    def __init__(self):
        self.rows = {}
        self.fail = False

    async def load(self, run_id):
        if self.fail:
            raise OSError("database unavailable")
        return copy.deepcopy(self.rows.get(run_id))

    async def save(self, run_id, payload, expected_revision):
        if self.fail:
            raise OSError("database unavailable")
        prior = self.rows.get(run_id)
        assert (prior[0] if prior else None) == expected_revision
        revision = (expected_revision or 0) + 1
        self.rows[run_id] = revision, copy.deepcopy(payload)
        return revision


class Provider:
    def __init__(self, *, missing=False, failure=None):
        self.missing, self.failure, self.calls = missing, failure, 0

    async def invoke(self, **kwargs):
        self.calls += 1
        await asyncio.sleep(0)
        if self.failure:
            raise self.failure
        return AIMessage(
            content="ok",
            usage_metadata=None
            if self.missing
            else {"input_tokens": 70, "output_tokens": 12, "total_tokens": 82},
        )


def gateway(provider, store, tick):
    return RunBudgetModelGateway(
        provider,
        max_calls=3,
        run_id="run-1",
        store=store,
        wall_clock=lambda: tick[0],
        max_seconds=10,
        finishing_seconds=5,
    )


async def call(model, role="researcher"):
    return await model.invoke(
        role=role, messages=task_messages(instruction="instruction", task="task")
    )


@pytest.mark.asyncio
async def test_restart_keeps_consumed_calls_and_measured_usage():
    store, tick, provider = SnapshotStore(), [100.0], Provider()
    await call(gateway(provider, store, tick))
    resumed = gateway(provider, store, tick)
    with pytest.raises(RuntimeError, match="budget_exhausted:model_calls"):
        await call(resumed)
    await call(resumed, "responder")
    usage = resumed.usage_payload()
    assert provider.calls == 2
    assert usage["input_tokens"] == 140
    assert usage["output_tokens"] == 24
    assert usage["role_usage"]["researcher"]["total_tokens"] == 82
    assert usage["role_usage"]["writer"]["total_tokens"] == 82


@pytest.mark.asyncio
async def test_quota_block_survives_restart_without_poisoning_a_new_run():
    from deeptrace.domain import ErrorCategory
    from deeptrace.harness.model_gateway import ModelCallError
    store, tick = SnapshotStore(), [100.0]
    failed = Provider(failure=ModelCallError(ErrorCategory.FATAL, code='model_quota_exhausted'))
    with pytest.raises(ModelCallError):
        await call(gateway(failed, store, tick))
    healthy = Provider()
    with pytest.raises(ModelCallError, match='model_quota_exhausted'):
        await call(gateway(healthy, store, tick), 'responder')
    assert healthy.calls == 0
    await call(RunBudgetModelGateway(healthy, run_id='new-run', store=store, wall_clock=lambda:tick[0]))
    assert healthy.calls == 1


@pytest.mark.asyncio
async def test_restart_keeps_original_deadline_including_downtime():
    store, tick, provider = SnapshotStore(), [100.0], Provider()
    await call(gateway(provider, store, tick))
    tick[0] = 116
    with pytest.raises(RuntimeError, match="budget_exhausted:elapsed_time"):
        await call(gateway(provider, store, tick), "responder")
    assert provider.calls == 1


@pytest.mark.asyncio
async def test_unknown_usage_is_not_reported_as_zero_or_a_measured_estimate():
    store, tick, provider = SnapshotStore(), [100.0], Provider(missing=True)
    model = gateway(provider, store, tick)
    await call(model)
    assert model.usage_payload()["input_tokens"] is None
    assert model.usage_payload()["output_tokens"] is None
    assert model.usage_payload()["missing_usage_attempts"] == 1
    assert model.used_input_tokens > 0


@pytest.mark.asyncio
async def test_unavailable_snapshot_storage_prevents_dispatch():
    store, tick, provider = SnapshotStore(), [100.0], Provider()
    store.fail = True
    with pytest.raises(RuntimeError, match="budget_state_unavailable"):
        await call(gateway(provider, store, tick))
    assert provider.calls == 0


@pytest.mark.asyncio
async def test_failed_attempt_is_charged_across_restart():
    store, tick = SnapshotStore(), [100.0]
    with pytest.raises(RuntimeError, match="provider failed"):
        await call(
            gateway(Provider(failure=RuntimeError("provider failed")), store, tick)
        )
    provider = Provider()
    with pytest.raises(RuntimeError, match="budget_exhausted:model_calls"):
        await call(gateway(provider, store, tick))
    assert provider.calls == 0


@pytest.mark.asyncio
async def test_unknown_role_usage_is_included_in_role_totals():
    from deeptrace.models.metrics import UsageBreakdown

    model = RunBudgetModelGateway(Provider())
    await call(model, "document_reader")
    roles = UsageBreakdown.model_validate(model.usage_payload()["role_usage"])
    assert roles.total.total_tokens == 82


@pytest.mark.asyncio
async def test_invalid_snapshot_limits_cannot_reopen_dispatch():
    store, tick, provider = SnapshotStore(), [100.0], Provider()
    await call(gateway(provider, store, tick))
    store.rows["run-1"][1]["finishing_calls"] = 20
    with pytest.raises(RuntimeError, match="budget_state_unavailable"):
        await call(gateway(provider, store, tick), "responder")
    assert provider.calls == 1


@pytest.mark.asyncio
async def test_model_events_keep_usage_without_prompt_or_provider_text():
    from deeptrace.observability.events import HarnessEventRecorder

    events = HarnessEventRecorder()
    model = RunBudgetModelGateway(Provider(), event_sink=events, run_id="run-1")
    await model.invoke(
        role="researcher",
        messages=task_messages(instruction="private instruction", task="private task"),
    )
    assert [event["event_type"] for event in events.events] == [
        "model.started",
        "model.completed",
    ]
    payload = events.events[-1]["payload"]
    assert payload["input_tokens"] == 70
    assert payload["output_tokens"] == 12
    assert payload["call_id"] == "run-1:1"
    assert "private" not in str(events.events)


@pytest.mark.asyncio
async def test_unavailable_budget_usage_is_unknown_instead_of_complete_zero():
    store, provider = SnapshotStore(), Provider()
    store.fail = True
    model = gateway(provider, store, [100.0])
    with pytest.raises(RuntimeError, match="budget_state_unavailable"):
        await call(model)
    assert model.usage_payload()["total_tokens"] is None
    assert model.usage_payload()["usage_complete"] is False


@pytest.mark.asyncio
async def test_snapshot_save_failure_prevents_provider_dispatch():
    class SaveFailure(SnapshotStore):
        async def save(self, *args):
            raise OSError("database unavailable")

    provider = Provider()
    with pytest.raises(RuntimeError, match="budget_state_unavailable"):
        await call(gateway(provider, SaveFailure(), [100.0]))
    assert provider.calls == 0


@pytest.mark.asyncio
async def test_cancelled_call_consumption_survives_restart():
    store, tick = SnapshotStore(), [100.0]
    model = gateway(Provider(failure=asyncio.CancelledError()), store, tick)
    with pytest.raises(asyncio.CancelledError):
        await call(model)
    resumed = gateway(Provider(), store, tick)
    with pytest.raises(RuntimeError, match="budget_exhausted:model_calls"):
        await call(resumed)
    assert resumed.usage_payload()["missing_usage_attempts"] == 1


@pytest.mark.asyncio
async def test_other_role_preserves_measured_usage():
    model = RunBudgetModelGateway(Provider())
    await call(model, "other")
    assert model.usage_payload()["role_usage"]["other"]["total_tokens"] == 82


def test_malformed_usage_is_unknown():
    from types import SimpleNamespace

    from deeptrace.observability.model_metrics import response_usage

    assert response_usage(SimpleNamespace(usage_metadata="invalid")) is None
