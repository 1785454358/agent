import asyncio

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from deeptrace.harness.model_gateway import ChatModelGateway, ModelCallError


def valid_messages():
    return [
        SystemMessage(content="研究要求"),
        HumanMessage(content="原始任务：task\n当前约束：none"),
    ]


class TransientThenSuccessModel:
    def __init__(self):
        self.attempts = 0

    def bind_tools(self, tools):
        return self

    def bind(self, **kwargs):
        return self

    async def ainvoke(self, messages):
        self.attempts += 1
        if self.attempts == 1:
            raise TimeoutError("secret-error-not-for-journal")
        return AIMessage(
            content="answer",
            usage_metadata={"input_tokens": 7, "output_tokens": 3, "total_tokens": 10},
        )


@pytest.mark.asyncio
async def test_parallel_budget_reservations_do_not_exceed_limit():
    from deeptrace.eval.telemetry import RequestCounter, RequestLimitReached

    counter = RequestCounter(3)

    async def request():
        try:
            counter.reserve()
        except RequestLimitReached:
            return False
        await asyncio.sleep(0)
        return True

    assert sum(await asyncio.gather(*(request() for _ in range(20)))) == 3
    assert counter.used == 3


def test_two_scope_reservation_does_not_spend_when_batch_is_exhausted():
    from deeptrace.eval.telemetry import RequestCounter, RequestLimitReached

    run = RequestCounter(3)
    batch = RequestCounter(1, used=1)
    with pytest.raises(RequestLimitReached):
        run.reserve(batch)
    assert run.used == 0


@pytest.mark.asyncio
async def test_attempt_limit_applies_to_transport_retries():
    from deeptrace.eval.telemetry import (
        MeteredChatModel,
        ModelTelemetry,
        RequestCounter,
    )

    meter = ModelTelemetry()
    wrapped = MeteredChatModel(
        TransientThenSuccessModel(), meter, RequestCounter(1), RequestCounter(3)
    )
    gateway = ChatModelGateway(wrapped, retry_attempts=2, retry_base_seconds=0)
    with pytest.raises(ModelCallError):
        await gateway.invoke(role="writer", messages=valid_messages())
    summary = meter.snapshot()
    assert summary["provider_attempts"] == 1
    assert summary["input_tokens"] is None
    assert summary["missing_usage_attempts"] == 1
    assert "secret-error" not in str(summary)


@pytest.mark.asyncio
async def test_retry_success_reports_observed_usage_not_fake_complete_totals():
    from deeptrace.eval.telemetry import (
        MeteredChatModel,
        ModelTelemetry,
        RequestCounter,
    )

    meter = ModelTelemetry()
    wrapped = MeteredChatModel(
        TransientThenSuccessModel(), meter, RequestCounter(3), RequestCounter(3)
    )
    gateway = ChatModelGateway(wrapped, retry_attempts=2, retry_base_seconds=0)
    response = await gateway.invoke(role="writer", messages=valid_messages())
    assert response.content == "answer"
    summary = meter.snapshot()
    assert summary["provider_attempts"] == 2
    assert summary["observed_input_tokens"] == 7
    assert summary["observed_output_tokens"] == 3
    assert summary["input_tokens"] is None
    assert summary["missing_usage_attempts"] == 1


@pytest.mark.asyncio
async def test_bound_models_share_transport_ledger_and_preserve_usage():
    from deeptrace.eval.telemetry import (
        MeteredChatModel,
        ModelTelemetry,
        RequestCounter,
        RequestLimitReached,
    )

    raw = TransientThenSuccessModel()
    raw.attempts = 1
    meter = ModelTelemetry()
    wrapped = MeteredChatModel(raw, meter, RequestCounter(1), RequestCounter(2))
    await (
        wrapped.bind_tools([{"name": "tool"}])
        .bind(temperature=0)
        .ainvoke(valid_messages())
    )
    with pytest.raises(RequestLimitReached):
        await wrapped.ainvoke(valid_messages())
    assert meter.snapshot()["input_tokens"] == 7
    assert meter.snapshot()["output_tokens"] == 3


@pytest.mark.asyncio
async def test_cancelled_transport_is_not_refunded_or_swallowed():
    from deeptrace.eval.telemetry import (
        MeteredChatModel,
        ModelTelemetry,
        RequestCounter,
    )

    class CancelledModel:
        async def ainvoke(self, messages):
            raise asyncio.CancelledError

    meter = ModelTelemetry()
    counter = RequestCounter(1)
    with pytest.raises(asyncio.CancelledError):
        await MeteredChatModel(
            CancelledModel(), meter, counter, RequestCounter(2)
        ).ainvoke(valid_messages())
    assert counter.used == 1
    assert meter.snapshot()["attempts"][0]["status"] == "cancelled"


def test_malformed_and_absent_usage_remain_unknown():
    from deeptrace.eval.telemetry import ModelTelemetry

    class BadResponse:
        usage_metadata = {"input_tokens": True, "output_tokens": -1}

    meter = ModelTelemetry()
    meter.finish(meter.start(), BadResponse())
    meter.finish(meter.start(), AIMessage(content="missing"))
    assert meter.snapshot()["input_tokens"] is None
    assert meter.snapshot()["missing_usage_attempts"] == 2
