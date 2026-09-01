from datetime import UTC, datetime

import pytest

from deeptrace.models import (
    RawDocument,
    ResearchNote,
    ResearchPlan,
    ResearchTask,
    ScraperUsed,
    SectionResult,
    TaskCompletion,
    TaskCoverage,
)


@pytest.fixture
def research_task() -> ResearchTask:
    return ResearchTask(
        task_id="task-01",
        section_id="section-01",
        title="技术进展",
        question="有哪些技术进展？",
        planned_queries=["AI Agent 技术进展"],
        expected_topics=["规划", "工具调用"],
        min_sources=2,
    )


@pytest.fixture
def task_coverage(research_task: ResearchTask) -> TaskCoverage:
    return TaskCoverage(task_id=research_task.task_id)


@pytest.fixture
def running_coverage(research_task: ResearchTask) -> TaskCoverage:
    return TaskCoverage(task_id=research_task.task_id, status="running")


@pytest.fixture
def task_completion(research_task: ResearchTask) -> TaskCompletion:
    return TaskCompletion(
        task_id=research_task.task_id,
        summary="完成技术研究",
        covered_topics=["规划", "工具调用"],
        unresolved_topics=[],
    )


@pytest.fixture
def research_note(research_task: ResearchTask) -> ResearchNote:
    return ResearchNote(
        note_id="note-01",
        doc_id="doc-01",
        task_id=research_task.task_id,
        section_id=research_task.section_id,
        active_query="AI Agent 技术进展",
        title="来源标题",
        key_points=["关键进展"],
        evidence_snippets=["原文摘录"],
        source_url="https://example.com/a",
        relevance_score=0.8,
        compression_status="compressed",
    )


@pytest.fixture
def research_plan(research_task: ResearchTask) -> ResearchPlan:
    second = research_task.model_copy(
        update={
            "task_id": "task-02",
            "section_id": "section-02",
            "title": "应用进展",
        }
    )
    return ResearchPlan(
        plan_id="plan-01",
        original_query="年度进展",
        normalized_query="年度进展",
        objective="总结年度进展",
        language="zh-CN",
        tasks=[research_task, second],
        report_outline=["技术进展", "应用进展"],
    )


@pytest.fixture
def section_result(
    research_task: ResearchTask, research_note: ResearchNote
) -> SectionResult:
    coverage = TaskCoverage(
        task_id=research_task.task_id,
        status="sufficient",
        successful_source_urls=[research_note.source_url],
        relevant_note_ids=[research_note.note_id],
    )
    return SectionResult(
        task_id=research_task.task_id,
        section_id=research_task.section_id,
        title=research_task.title,
        summary="完成技术研究",
        note_ids=[research_note.note_id],
        source_urls=[research_note.source_url],
        coverage=coverage,
    )


@pytest.fixture
def partial_section(section_result: SectionResult) -> SectionResult:
    return section_result.model_copy(
        update={
            "coverage": section_result.coverage.model_copy(
                update={"status": "partial", "failure_reason": "token_budget"}
            )
        }
    )


@pytest.fixture
def raw_document() -> RawDocument:
    return RawDocument(
        doc_id="doc-01",
        requested_url="https://example.com/a",
        final_url="https://example.com/a",
        canonical_url="https://example.com/a",
        title="来源标题",
        content="整页正文唯一标记",
        content_hash="hash",
        fetched_at=datetime.now(UTC),
        scraper_used=ScraperUsed.HTTPX_TRAFILATURA,
        status="success",
    )
