import asyncio

import pytest
from deeptrace.harness.model_gateway import ChatModelGateway
from deeptrace.harness.prompts import task_messages
from langchain_core.messages import AIMessage, HumanMessage


class Provider:
    def __init__(self, *results):
        self.results = list(results)
        self.calls = 0

    async def ainvoke(self, messages):
        self.calls += 1
        result = self.results.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result


MESSAGES = task_messages(
    instruction="instruction",
    task="original task",
    constraints=["current constraint"],
)


@pytest.mark.asyncio
async def test_transport_timeout_retries_once():
    provider = Provider(TimeoutError(), AIMessage(content="ok"))
    gateway = ChatModelGateway(provider, retry_attempts=2, retry_base_seconds=0)
    assert (await gateway.invoke(role="researcher", messages=MESSAGES)).content == "ok"
    assert provider.calls == 2


@pytest.mark.asyncio
async def test_unknown_failure_is_sanitized_and_not_retried():
    provider = Provider(ValueError("private-key"))
    gateway = ChatModelGateway(provider, retry_attempts=2, retry_base_seconds=0)
    with pytest.raises(Exception) as caught:
        await gateway.invoke(role="researcher", messages=MESSAGES)
    assert "private-key" not in str(caught.value)
    assert provider.calls == 1
    assert caught.value.category.value == "fatal"


@pytest.mark.asyncio
async def test_gateway_does_not_retry_cancellation():
    provider = Provider(asyncio.CancelledError())
    with pytest.raises(asyncio.CancelledError):
        await ChatModelGateway(provider).invoke(role="researcher", messages=MESSAGES)
    assert provider.calls == 1


@pytest.mark.asyncio
async def test_gateway_rejects_a_model_call_without_the_context_envelope():
    provider = Provider(AIMessage(content="must not run"))
    gateway = ChatModelGateway(provider)

    with pytest.raises(ValueError, match="model_context_invariant"):
        await gateway.invoke(
            role="researcher", messages=[HumanMessage(content="task only")]
        )

    assert provider.calls == 0
