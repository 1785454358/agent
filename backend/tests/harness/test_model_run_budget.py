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
async def test_provider_quota_exhaustion_stops_later_roles_without_new_dispatches():
    from deeptrace.harness.model_gateway import ChatModelGateway, ModelCallError
    from harness.test_model_gateway import Provider as ChatProvider
    class QuotaError(RuntimeError):
        status_code = 429
        body = {'error': {'code':'credit_quota_exceeded'}}
    provider = ChatProvider(QuotaError())
    gateway = budgeted(ChatModelGateway(provider, retry_attempts=1))
    for role in ('planner', 'researcher', 'evaluator', 'responder'):
        with pytest.raises(ModelCallError):
            await call(gateway, role)
    assert gateway.research_exhausted
    assert provider.calls == gateway.used_calls == 1
    assert gateway.usage_payload()['provider_attempts'] == 1


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
async def test_final_review_has_a_call_reserved_within_the_existing_total_cap():
    provider = Provider()
    gateway = budgeted(provider, max_calls=5, finishing_calls=3)
    await call(gateway)
    await call(gateway)
    with pytest.raises(RuntimeError, match="budget_exhausted"):
        await call(gateway)
    await call(gateway, "evaluator")
    with pytest.raises(RuntimeError, match="budget_exhausted"):
        await call(gateway, "evaluator")
    await call(gateway, "responder")
    await call(gateway, "responder")
    with pytest.raises(RuntimeError, match="budget_exhausted"):
        await call(gateway, "responder")
    assert len(provider.calls) == 5


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
async def test_remaining_context_tracks_actual_usage_and_keeps_room_for_review():
    from deeptrace.harness.token_budget import TokenBudgetConfig, bounded_run_context

    gateway = budgeted(Provider(tokens=350), max_input_tokens=1000, finishing_input_reserve=500)
    config = TokenBudgetConfig(context_tokens=2000, output_reserve_tokens=50, safety_tokens=25)
    await call(gateway)
    assert await gateway.available_input_tokens("researcher") == 150
    assert await gateway.available_input_tokens("responder") == 650
    bounded = await bounded_run_context(gateway, "responder", config, remaining_calls=2)
    assert bounded.context_tokens == 400
    assert bounded.input_budget == 325
    assert config.context_tokens == 2000
    await call(gateway, "responder")
    assert await gateway.available_input_tokens("responder") == 300


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
