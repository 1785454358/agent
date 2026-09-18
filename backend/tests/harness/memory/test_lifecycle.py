from dataclasses import replace
from types import SimpleNamespace

import pytest
from deeptrace.domain import ConversationIntent
from deeptrace.harness.memory.lifecycle import _recall_memory
from strategies.fixtures import build_gateway_fixture


@pytest.mark.asyncio
async def test_optional_recall_failure_degrades_without_losing_task():
    class BrokenRetriever:
        async def recall(self, **kwargs):
            raise RuntimeError("unavailable")

    fixture = build_gateway_fixture()
    runtime = SimpleNamespace(
        context=replace(fixture.context, memory_retriever=BrokenRetriever())
    )
    result = await _recall_memory(
        {
            "turn": {"intent": ConversationIntent.RESEARCH, "user_input": "original"},
            "conversation": {"evidence_ids": []},
        },
        runtime,
    )
    assert result["turn"]["user_input"] == "original"
    assert result["turn"]["recalled_memories"] == []
    assert any(name == "memory.degraded" for name, _ in fixture.events.events)
