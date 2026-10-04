import asyncio

import pytest
from langchain_core.messages import AIMessage

from deeptrace.harness.model_budget import RunBudgetModelGateway
from deeptrace.harness.prompts import task_messages


class Provider:
    def __init__(self, *, tokens=50, fail=False):
        self.calls = []
        self.tokens = tokens
        self.fail = fail

    async def invoke(self, **kwargs):
        self.calls.append(kwargs["role"])
        await asyncio.sleep(0)
        if self.fail:
            raise RuntimeError("provider unavailable")
        return AIMessage(content="ok", usage_metadata={"input_tokens": self.tokens,
            "output_tokens": 1, "total_tokens": self.tokens + 1})


def budgeted(provider, **kwargs):
    return RunBudgetModelGateway(provider, **kwargs)


async def call(gateway, role="researcher", prompt="小任务"):
    return await gateway.invoke(role=role, messages=task_messages(instruction="研究", task=prompt))


@pytest.mark.asyncio
async def test_research_cannot_spend_the_two_calls_reserved_for_evaluation_and_answer():
    provider = Provider()
    gateway = budgeted(provider, max_calls=4)
    await call(gateway)
    await call(gateway)
    with pytest.raises(RuntimeError, match="budget_exhausted"):
        await call(gateway)
    await call(gateway, "evaluator")
    with pytest.raises(RuntimeError, match="budget_exhausted"):
        await call(gateway, "evaluator")
    await call(gateway, "responder")
    assert provider.calls == ["researcher", "researcher", "evaluator", "responder"]


@pytest.mark.asyncio
async def test_concurrent_research_calls_reserve_the_shared_run_budget_atomically():
    provider = Provider()
    gateway = budgeted(provider, max_calls=4)
    results = await asyncio.gather(*(call(gateway) for _ in range(5)), return_exceptions=True)
    assert sum(isinstance(r, AIMessage) for r in results) == 2
    assert len(provider.calls) == 2
    assert all(isinstance(r, RuntimeError) for r in results if not isinstance(r, AIMessage))


@pytest.mark.asyncio
async def test_provider_input_usage_limits_next_call_without_spending_writer_reserve():
    provider = Provider(tokens=350)
    gateway = budgeted(provider, max_input_tokens=1000, finishing_input_reserve=500)
    await call(gateway)
    with pytest.raises(RuntimeError, match="budget_exhausted"):
        await call(gateway, prompt="word " * 200)
    await call(gateway, "responder")
    assert provider.calls == ["researcher", "responder"]


@pytest.mark.asyncio
async def test_failed_provider_attempts_still_consume_call_allowance():
    provider = Provider(fail=True)
    gateway = budgeted(provider, max_calls=3)
    with pytest.raises(RuntimeError, match="provider unavailable"):
        await call(gateway)
    with pytest.raises(RuntimeError, match="budget_exhausted"):
        await call(gateway)
    assert len(provider.calls) == 1


@pytest.mark.asyncio
async def test_elapsed_research_window_leaves_a_separate_finishing_window():
    provider = Provider()
    tick = [0.0]
    gateway = budgeted(provider, max_seconds=10, finishing_seconds=5, monotonic=lambda: tick[0])
    tick[0] = 11
    with pytest.raises(RuntimeError, match="budget_exhausted"):
        await call(gateway)
    await call(gateway, "responder")
    tick[0] = 16
    with pytest.raises(RuntimeError, match="budget_exhausted"):
        await call(gateway, "responder")
