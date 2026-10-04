import pytest

from deeptrace.config import Settings
from tests.eval.test_telemetry import TransientThenSuccessModel, valid_messages


@pytest.mark.asyncio
async def test_real_factory_instruments_bound_provider_and_resumed_batch_budget(
    monkeypatch,
):
    import langchain_openai

    from deeptrace.eval.experiment import EvaluationLimits
    from deeptrace.eval.real import build_real_model_factory
    from deeptrace.eval.telemetry import RequestCounter
    from deeptrace.harness.model_gateway import ModelCallError

    monkeypatch.setattr(
        langchain_openai, "ChatOpenAI", lambda **kwargs: TransientThenSuccessModel()
    )
    limits = EvaluationLimits(max_provider_attempts=4, max_batch_provider_attempts=2)
    factory = build_real_model_factory(
        Settings(
            openai_api_key="test-only",
            openai_base_url="https://example.org/v1",
            openai_model="test",
            tavily_api_key="",
            openai_max_tokens=2048,
        ),
        limits=limits,
        batch_counter=RequestCounter(2, used=1),
    )
    gateway = factory()
    with pytest.raises(ModelCallError):
        await gateway.invoke(
            role="writer", messages=valid_messages(), tools=[{"name": "tool"}]
        )
    assert gateway.telemetry.snapshot()["provider_attempts"] == 1
