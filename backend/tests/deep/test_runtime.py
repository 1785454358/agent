from types import SimpleNamespace
import asyncio

import pytest

from deeptrace.deep.runtime import RunRuntime


def test_elapsed_time_and_token_usage_never_stop_model_calls(monkeypatch):
    now = [100.0]
    monkeypatch.setattr("deeptrace.deep.runtime.time.monotonic", lambda: now[0])
    runtime = RunRuntime(
        SimpleNamespace(max_runtime_seconds=100, writer_timeout_seconds=60)
    )
    now[0] = 100000.0

    class Model:
        async def ainvoke(self, messages):
            from langchain_core.messages import AIMessage

            return AIMessage(
                content="ok",
                usage_metadata={
                    "input_tokens": 100000,
                    "output_tokens": 1,
                    "total_tokens": 100001,
                },
            )

    response = asyncio.run(runtime.invoke(Model(), [], "executor"))
    assert response.content == "ok"
    assert runtime.role_usage.total.total_tokens == 100001


def test_individual_model_request_still_has_a_fault_timeout():
    class Model:
        async def ainvoke(self, messages):
            await asyncio.Event().wait()

    async def run():
        runtime = RunRuntime(SimpleNamespace(deep_call_timeout_seconds=0.01))
        with pytest.raises(TimeoutError):
            await runtime.invoke(Model(), [], "executor")

    asyncio.run(run())
