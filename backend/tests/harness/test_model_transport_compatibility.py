"""Real exception types at the gateway boundary; no external API requests."""

import asyncio

import httpx
import pytest
from deeptrace.domain import ErrorCategory
from deeptrace.eval.telemetry import (
    MeteredChatModel,
    ModelTelemetry,
    RequestCounter,
    RequestLimitReached,
)
from deeptrace.harness.model_gateway import ChatModelGateway, ModelCallError
from deeptrace.harness.prompts import task_messages
from langchain_core.messages import AIMessage
from langchain_openai.chat_models.base import (
    OpenAIAuthenticationError,
    OpenAIConnectionError,
    OpenAIInvalidRequestError,
    OpenAITimeoutError,
)

REQUEST = httpx.Request("POST", "https://provider.invalid/v1/chat/completions")
MESSAGES = task_messages(
    instruction="instruction", task="original task", constraints=["current constraint"]
)
TRANSPORT_ERRORS = [OpenAIConnectionError, OpenAITimeoutError]


class Provider:
    """Only the network-facing call is replaced; gateway and metering stay real."""

    def __init__(self, *results):
        self.results = list(results)
        self.calls = 0

    async def ainvoke(self, messages):
        assert messages == MESSAGES
        self.calls += 1
        result = self.results.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result


@pytest.mark.asyncio
@pytest.mark.parametrize("error_type", TRANSPORT_ERRORS)
async def test_wrapper_connection_or_timeout_recovers(error_type):
    provider = Provider(error_type(request=REQUEST), AIMessage(content="recovered"))

    response = await ChatModelGateway(provider, retry_base_seconds=0).invoke(
        role="researcher", messages=MESSAGES
    )

    assert response.content == "recovered"
    assert provider.calls == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("error_type", TRANSPORT_ERRORS)
async def test_persistent_wrapper_failure_is_bounded_and_transient(error_type):
    errors = [error_type(request=REQUEST) for _ in range(3)]
    provider = Provider(*errors)

    with pytest.raises(ModelCallError, match="^model_request_failed$") as caught:
        await ChatModelGateway(provider, retry_base_seconds=0).invoke(
            role="researcher", messages=MESSAGES
        )

    assert caught.value.category == ErrorCategory.TRANSIENT
    assert provider.calls == 2
    assert len(provider.results) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error_type", "status"),
    [(OpenAIAuthenticationError, 401), (OpenAIInvalidRequestError, 400)],
)
async def test_authentication_and_invalid_requests_remain_fatal(error_type, status):
    error = error_type(
        message="private-key",
        response=httpx.Response(status, request=REQUEST),
        body=None,
    )
    provider = Provider(error, AIMessage(content="must not run"))

    with pytest.raises(ModelCallError) as caught:
        await ChatModelGateway(provider, retry_base_seconds=0).invoke(
            role="researcher", messages=MESSAGES
        )

    assert caught.value.category == ErrorCategory.FATAL
    assert "private-key" not in str(caught.value)
    assert provider.calls == 1


@pytest.mark.asyncio
async def test_budget_sentinel_is_not_retried():
    provider = Provider(RequestLimitReached(), AIMessage(content="must not run"))

    with pytest.raises(ModelCallError) as caught:
        await ChatModelGateway(provider, retry_base_seconds=0).invoke(
            role="researcher", messages=MESSAGES
        )

    assert caught.value.category == ErrorCategory.FATAL
    assert provider.calls == 1


@pytest.mark.asyncio
async def test_cancellation_is_propagated_without_retry():
    provider = Provider(asyncio.CancelledError(), AIMessage(content="must not run"))

    with pytest.raises(asyncio.CancelledError):
        await ChatModelGateway(provider, retry_base_seconds=0).invoke(
            role="researcher", messages=MESSAGES
        )

    assert provider.calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("error_type", TRANSPORT_ERRORS)
async def test_wrapper_retry_spends_both_provider_attempts(error_type):
    provider = Provider(
        error_type(request=REQUEST),
        AIMessage(
            content="recovered",
            usage_metadata={"input_tokens": 7, "output_tokens": 3, "total_tokens": 10},
        ),
    )
    meter = ModelTelemetry()
    run_counter, batch_counter = RequestCounter(2), RequestCounter(2)
    wrapped = MeteredChatModel(provider, meter, run_counter, batch_counter)

    response = await ChatModelGateway(wrapped, retry_base_seconds=0).invoke(
        role="researcher", messages=MESSAGES
    )

    assert response.content == "recovered"
    assert run_counter.used == batch_counter.used == 2
    summary = meter.snapshot()
    assert summary["provider_attempts"] == 2
    assert summary["missing_usage_attempts"] == 1
    assert summary["observed_input_tokens"] == 7
    assert summary["observed_output_tokens"] == 3
    assert summary["input_tokens"] is None
    assert summary["output_tokens"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("error_type", TRANSPORT_ERRORS)
@pytest.mark.parametrize("limited_scope", ["run", "batch"])
async def test_wrapper_retry_cannot_bypass_provider_ceiling(error_type, limited_scope):
    provider = Provider(error_type(request=REQUEST), AIMessage(content="must not run"))
    meter = ModelTelemetry()
    run_counter = RequestCounter(1 if limited_scope == "run" else 2)
    batch_counter = RequestCounter(1 if limited_scope == "batch" else 2)
    wrapped = MeteredChatModel(provider, meter, run_counter, batch_counter)

    with pytest.raises(ModelCallError) as caught:
        await ChatModelGateway(wrapped, retry_base_seconds=0).invoke(
            role="researcher", messages=MESSAGES
        )

    assert caught.value.category == ErrorCategory.FATAL
    assert isinstance(caught.value.__cause__, RequestLimitReached)
    assert provider.calls == 1
    assert run_counter.used == batch_counter.used == 1
    assert meter.snapshot()["provider_attempts"] == 1
    assert meter.snapshot()["missing_usage_attempts"] == 1
