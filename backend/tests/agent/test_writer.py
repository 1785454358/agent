import asyncio
from types import SimpleNamespace

from deeptrace.agent.writer import (
    WriterAgent,
    citation_numbers,
    find_unqualified_year_mentions,
    is_language_consistent,
)


def _run(awaitable):
    return asyncio.run(awaitable)


def _note(**updates):
    from deeptrace.models import ResearchNote

    note = ResearchNote(
        note_id="note-01",
        doc_id="doc-01",
        task_id="task-01",
        section_id="section-01",
        active_query="AI Agent 技术进展",
        title="来源标题",
        key_points=["关键进展"],
        evidence_snippets=["原文摘录。"],
        source_url="https://example.com/a",
        relevance_score=0.8,
        compression_status="compressed",
    )
    return note.model_copy(update=updates)


class ScriptedModel:
    """按脚本返回 Markdown 正文，并记录收到的消息。"""

    def __init__(self, bodies: list[str]) -> None:
        self._bodies = bodies
        self.calls = 0
        self.messages: list[list] = []

    async def ainvoke(self, messages):
        self.calls += 1
        self.messages.append(messages)
        body = self._bodies[min(self.calls, len(self._bodies)) - 1]
        return SimpleNamespace(
            content=body,
            usage_metadata={"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
        )


class HangingModel:
    """模拟 Provider 已接收请求但永不返回。"""

    def __init__(self) -> None:
        self.calls = 0

    async def ainvoke(self, _messages):
        self.calls += 1
        await asyncio.Event().wait()


GOOD_BODY = "# 2024 年智能体进展\n\n## 技术进展\n\n- 关键进展[^1]。"


def test_writer_quality_validators() -> None:
    assert not is_language_consistent("Only English text about agents.", "zh-CN")
    assert is_language_consistent("这是关于智能体领域的重要进展报告。", "zh-CN")
    assert find_unqualified_year_mentions(
        "OpenAI Presence 于 2026 年发布。", 2024, 2024
    ) == [2026]
    assert find_unqualified_year_mentions(
        "后续回顾：Presence 于 2026 年发布，不属于 2024 年进展。",
        2024,
        2024,
    ) == []


def test_citation_numbers_extracted_from_body_only() -> None:
    body = "- 一[^1]；二[^2][^3]。"
    assert citation_numbers(body) == {1, 2, 3}
    assert citation_numbers("没有引用") == set()


def test_awrite_returns_mechanical_source_section(research_plan, section_result) -> None:
    model = ScriptedModel([GOOD_BODY])
    agent = WriterAgent(model)

    outcome = _run(
        agent.awrite(
            plan=research_plan,
            sections=[section_result],
            notes_by_section={"task-01": [_note()]},
            termination_reason="completed",
        )
    )

    assert model.calls == 1
    assert outcome.used_fallback is False
    assert outcome.sources == ["https://example.com/a"]
    assert outcome.used_note_ids == ["note-01"]
    assert outcome.usage.total_tokens == 2
    assert "[^1]: [来源标题](https://example.com/a)" in outcome.markdown
    assert "## 来源" in outcome.markdown


def test_awrite_retries_invalid_citation_then_succeeds(
    research_plan, section_result
) -> None:
    model = ScriptedModel(["- 无效引用[^9]。", GOOD_BODY])
    agent = WriterAgent(model)

    outcome = _run(
        agent.awrite(
            plan=research_plan,
            sections=[section_result],
            notes_by_section={"task-01": [_note()]},
            termination_reason="completed",
        )
    )

    assert model.calls == 2
    assert outcome.used_fallback is False
    assert outcome.usage.total_tokens == 4


def test_awrite_falls_back_after_second_invalid_output(
    research_plan, section_result
) -> None:
    model = ScriptedModel(["- 无效引用[^9]。", "- 仍然无效[^8]。"])
    agent = WriterAgent(model)

    outcome = _run(
        agent.awrite(
            plan=research_plan,
            sections=[section_result],
            notes_by_section={"task-01": [_note()]},
            termination_reason="completed",
        )
    )

    assert model.calls == 2
    assert outcome.used_fallback is True
    assert "关键进展[^1]" in outcome.markdown
    assert "[^1]: [来源标题](https://example.com/a)" in outcome.markdown


def test_awrite_falls_back_when_provider_exceeds_total_timeout(
    research_plan, section_result
) -> None:
    model = HangingModel()
    agent = WriterAgent(model, call_timeout_seconds=0.01)

    outcome = _run(
        asyncio.wait_for(
            agent.awrite(
                plan=research_plan,
                sections=[section_result],
                notes_by_section={"task-01": [_note()]},
                termination_reason="time_budget",
            ),
            timeout=0.2,
        )
    )

    assert model.calls == 1
    assert outcome.used_fallback is True
    assert "关键进展[^1]" in outcome.markdown
    assert "[^1]: [来源标题](https://example.com/a)" in outcome.markdown


def test_awrite_without_material_skips_model(research_plan, section_result) -> None:
    model = ScriptedModel([GOOD_BODY])
    agent = WriterAgent(model)

    outcome = _run(
        agent.awrite(
            plan=research_plan,
            sections=[section_result],
            notes_by_section={"task-01": []},
            termination_reason="time_budget",
        )
    )

    assert model.calls == 0
    assert outcome.used_fallback is True
    assert outcome.sources == []
    assert "局限" in outcome.markdown



def test_duplicate_urls_share_one_source_number(research_plan) -> None:
    from deeptrace.models import SectionResult, TaskCoverage

    note_a = _note()
    note_b = _note(note_id="note-02", doc_id="doc-02")
    second_section = SectionResult(
        task_id="task-02",
        section_id="section-02",
        title="应用进展",
        summary="完成应用研究",
        coverage=TaskCoverage(task_id="task-02"),
        note_ids=[note_b.note_id],
        source_urls=[note_b.source_url],
    )
    agent = WriterAgent(ScriptedModel([GOOD_BODY]))

    sources, numbers = agent._numbered_sources(
        [research_plan.tasks[0], research_plan.tasks[1]],
        {"task-01": [note_a], "task-02": [note_b]},
    )

    assert len(sources) == 1
    assert numbers[note_a.source_url] == 1
