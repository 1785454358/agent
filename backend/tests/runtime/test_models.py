from datetime import UTC, datetime

from deeptrace.models import AgentResult, TokenUsage, UsageBreakdown
from deeptrace.runtime.models import JobMessage, RunRecord, StoredEvent


def test_run_record_has_stable_defaults() -> None:
    run = RunRecord(
        id="run-1",
        question="研究问题",
        mode="multi_agent",
        created_at=datetime.now(UTC),
    )

    assert run.status == "pending"
    assert run.attempt_count == 0
    assert run.version == 0
    assert run.sources == []
    assert run.unresolved_gaps == []
    assert run.lease_owner is None
    assert run.lease_expires_at is None


def test_job_and_event_are_serializable() -> None:
    job = JobMessage(message_id="1-0", run_id="run-1")
    event = StoredEvent(
        id=7,
        run_id="run-1",
        event_type="planning.started",
        payload={"message": "开始规划", "details": {}},
        created_at=datetime.now(UTC),
    )

    assert job.model_dump(mode="json") == {
        "message_id": "1-0",
        "run_id": "run-1",
    }
    assert event.model_dump(mode="json")["id"] == 7


def test_agent_result_defaults_to_no_unresolved_gaps() -> None:
    result = AgentResult(
        status="completed",
        answer="报告",
        sources=[],
        steps=1,
        events=[],
        termination_reason="completed",
        search_queries=[],
        provider_usage=TokenUsage(),
        role_usage=UsageBreakdown(),
        estimated_cost_usd=None,
        stage_seconds={},
    )

    assert result.unresolved_gaps == []
