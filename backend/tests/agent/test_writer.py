import asyncio
from types import SimpleNamespace

from deeptrace.agent.writer import WriterAgent


def _run(awaitable):
    return asyncio.run(awaitable)


class ScriptedModel:
    """Return scripted Provider results while retaining the real prompt boundary."""

    def __init__(self, results):
        self._results = list(results)
        self.calls = 0
        self.messages: list[list] = []

    async def ainvoke(self, messages):
        self.messages.append(messages)
        result = self._results[self.calls]
        self.calls += 1
        if isinstance(result, Exception):
            raise result
        return SimpleNamespace(
            content=result,
            usage_metadata={
                "input_tokens": 2,
                "output_tokens": 3,
                "total_tokens": 5,
            },
        )


class FailingIfCalledModel:
    async def ainvoke(self, _messages):
        raise AssertionError("empty context must not call the Provider")


class HangingModel:
    def __init__(self) -> None:
        self.calls = 0

    async def ainvoke(self, _messages):
        self.calls += 1
        await asyncio.Event().wait()


CONTEXT = (
    "Source: https://example.com/a\n"
    "Title: 来源标题\n"
    "Content: 可核对的网页原文。\n"
)


def test_writer_receives_source_title_content_context() -> None:
    model = ScriptedModel(["# 报告\n\n内容（[来源](https://example.com/a)）。"])

    outcome = _run(
        WriterAgent(model).awrite(
            question="研究问题",
            context=CONTEXT,
            sources=["https://example.com/a"],
            language="zh-CN",
        )
    )

    assert "研究问题" in model.messages[-1][-1].content
    assert CONTEXT.strip() in model.messages[-1][-1].content
    assert outcome.markdown.endswith(
        "## References\n\n- https://example.com/a"
    )
    assert outcome.sources == ["https://example.com/a"]
    assert outcome.usage.total_tokens == 5
    assert outcome.used_fallback is False
    assert not hasattr(outcome, "used_note_ids")


def test_writer_abstains_when_context_is_empty_without_calling_model() -> None:
    outcome = _run(
        WriterAgent(FailingIfCalledModel()).awrite(
            question="研究问题",
            context="  ",
            sources=[],
            language="zh-CN",
        )
    )

    assert outcome.used_fallback is True
    assert outcome.sources == []
    assert "研究问题" in outcome.markdown
    assert "未获得有效资料" in outcome.markdown


def test_writer_appends_unique_references_in_input_order() -> None:
    model = ScriptedModel(["# Report\n\nBody."])

    outcome = _run(
        WriterAgent(model).awrite(
            question="Question",
            context=CONTEXT,
            sources=[
                "https://example.com/b",
                "https://example.com/a",
                "https://example.com/b",
                "",
            ],
            language="en",
        )
    )

    assert outcome.sources == [
        "https://example.com/b",
        "https://example.com/a",
    ]
    assert outcome.markdown.endswith(
        "## References\n\n"
        "- https://example.com/b\n"
        "- https://example.com/a"
    )


def test_writer_retries_once_after_provider_failure() -> None:
    model = ScriptedModel(
        [RuntimeError("temporary failure"), "# 报告\n\n成功。"]
    )

    outcome = _run(
        WriterAgent(model).awrite(
            question="研究问题",
            context=CONTEXT,
            sources=["https://example.com/a"],
            language="zh-CN",
            termination_reason="completed",
        )
    )

    assert model.calls == 2
    assert outcome.used_fallback is False
    assert outcome.usage.total_tokens == 5


def test_writer_uses_one_deadline_for_all_attempts() -> None:
    model = HangingModel()

    outcome = _run(
        asyncio.wait_for(
            WriterAgent(model, call_timeout_seconds=0.01).awrite(
                question="研究问题",
                context=CONTEXT,
                sources=["https://example.com/a"],
                language="zh-CN",
                termination_reason="time_budget",
            ),
            timeout=0.2,
        )
    )

    assert model.calls == 1
    assert outcome.used_fallback is True
    assert "time_budget" in outcome.markdown


def test_writer_fallback_includes_bounded_context_and_references() -> None:
    model = ScriptedModel([RuntimeError("down"), RuntimeError("still down")])

    outcome = _run(
        WriterAgent(model, context_limit_chars=12).awrite(
            question="研究问题",
            context="ABCDEFGHIJKL--MUST-BE-TRUNCATED",
            sources=["https://example.com/a"],
            language="zh-CN",
            termination_reason="provider_failure",
        )
    )

    assert model.calls == 2
    assert outcome.used_fallback is True
    assert "研究问题" in outcome.markdown
    assert "局限" in outcome.markdown
    assert "ABCDEFGHIJKL" in outcome.markdown
    assert "MUST-BE-TRUNCATED" not in outcome.markdown
    assert outcome.markdown.endswith(
        "## References\n\n- https://example.com/a"
    )
