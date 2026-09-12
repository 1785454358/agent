from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio

from deeptrace.models import AgentResult, RunEvent, TokenUsage, UsageBreakdown
from deeptrace.persistence.database import create_session_factory
from deeptrace.persistence.orm import Base
from deeptrace.persistence.repository import SqlAlchemyRunRepository
from deeptrace.runtime.models import RunRecord


@pytest_asyncio.fixture
async def repository():
    engine, sessions = create_session_factory("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield SqlAlchemyRunRepository(sessions)
    await engine.dispose()


@pytest.mark.asyncio
async def test_repository_creates_and_reads_run(repository) -> None:
    created_at = datetime.now(UTC)
    run = RunRecord(
        id="run-1",
        question="研究问题",
        mode="deep",
        created_at=created_at,
        request_payload={"question": "研究问题", "mode": "deep"},
    )

    await repository.create(run)
    loaded = await repository.get("run-1")

    assert loaded is not None
    assert loaded.id == "run-1"
    assert loaded.question == "研究问题"
    assert loaded.mode == "plan_execute"
    assert loaded.status == "pending"
    assert loaded.request_payload == {"question": "研究问题", "mode": "deep"}


@pytest.mark.asyncio
async def test_repository_lists_newest_runs_first_with_limit(repository) -> None:
    await repository.create(
        RunRecord(
            id="older",
            question="较早",
            created_at=datetime(2026, 9, 7, 8, 0, tzinfo=UTC),
        )
    )
    await repository.create(
        RunRecord(
            id="newer",
            question="较新",
            created_at=datetime(2026, 9, 7, 9, 0, tzinfo=UTC),
        )
    )

    runs = await repository.list(limit=1)

    assert [run.id for run in runs] == ["newer"]


@pytest.mark.asyncio
async def test_repository_claim_prevents_a_second_active_worker(repository) -> None:
    await repository.create(
        RunRecord(id="run-1", question="问题", created_at=datetime.now(UTC))
    )

    claimed = await repository.claim("run-1", "worker-1", 60)
    duplicate = await repository.claim("run-1", "worker-2", 60)

    assert claimed is not None
    assert claimed.status == "running"
    assert claimed.attempt_count == 1
    assert claimed.version == 1
    assert claimed.lease_owner == "worker-1"
    assert claimed.lease_expires_at is not None
    assert duplicate is None


@pytest.mark.asyncio
async def test_repository_renews_only_the_current_worker_lease(repository) -> None:
    await repository.create(
        RunRecord(id="run-1", question="问题", created_at=datetime.now(UTC))
    )
    await repository.claim("run-1", "worker-1", 60)

    rejected = await repository.renew_lease("run-1", "worker-2", 120)
    renewed = await repository.renew_lease("run-1", "worker-1", 120)

    assert rejected is False
    assert renewed is True
    loaded = await repository.get("run-1")
    assert loaded is not None
    assert loaded.lease_owner == "worker-1"


@pytest.mark.asyncio
async def test_repository_returns_only_events_after_cursor(repository) -> None:
    await repository.create(
        RunRecord(id="run-1", question="问题", created_at=datetime.now(UTC))
    )
    first = await repository.append_event(
        "run-1", RunEvent(event_type="planning.started", message="开始")
    )
    second = await repository.append_event(
        "run-1", RunEvent(event_type="planning.completed", message="完成")
    )

    events = await repository.events_after("run-1", first.id)

    assert [item.id for item in events] == [second.id]
    assert events[0].event_type == "planning.completed"
    assert events[0].payload["message"] == "完成"
    assert events[0].payload["event_type"] == "planning.completed"
    assert "ts" in events[0].payload


@pytest.mark.asyncio
async def test_repository_requests_cancel_only_for_non_terminal_run(repository) -> None:
    await repository.create(
        RunRecord(id="active", question="问题", created_at=datetime.now(UTC))
    )
    await repository.create(
        RunRecord(
            id="done",
            question="问题",
            status="completed",
            created_at=datetime.now(UTC),
        )
    )

    active = await repository.request_cancel("active")
    done = await repository.request_cancel("done")

    assert active is not None
    assert active.status == "cancel_requested"
    cancellation_claim = await repository.claim("active", "worker-1", 60)
    assert cancellation_claim is not None
    assert cancellation_claim.status == "running"
    assert done is None
    assert await repository.request_cancel("missing") is None


@pytest.mark.asyncio
async def test_repository_only_current_worker_can_persist_result(repository) -> None:
    await repository.create(
        RunRecord(id="run-1", question="问题", created_at=datetime.now(UTC))
    )
    await repository.claim("run-1", "worker-1", 60)
    result = AgentResult(
        status="partial",
        answer="报告正文",
        sources=["https://example.com/a"],
        steps=4,
        events=[],
        termination_reason="incomplete_research",
        search_queries=["查询词"],
        provider_usage=TokenUsage(
            input_tokens=30, output_tokens=12, total_tokens=42
        ),
        role_usage=UsageBreakdown(writer=TokenUsage(total_tokens=42)),
        estimated_cost_usd=Decimal("0.01"),
        stage_seconds={"writer": 1.2},
        unresolved_gaps=["缺少官方来源"],
    )

    stale = await repository.complete("run-1", "worker-2", result)
    completed = await repository.complete("run-1", "worker-1", result)

    assert stale is None
    assert completed is not None
    assert completed.status == "partial"
    assert completed.answer == "报告正文"
    assert completed.sources == ["https://example.com/a"]
    assert completed.unresolved_gaps == ["缺少官方来源"]
    assert completed.usage == {
        "total_tokens": 42,
        "input_tokens": 30,
        "output_tokens": 12,
        "role_usage": {
            "planner": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            "executor": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            "replanner": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            "supervisor": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            "researcher": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            "writer": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 42},
        },
        "steps": 4,
        "estimated_cost_usd": "0.01",
        "stage_seconds": {"writer": 1.2},
    }
    assert completed.finished_at is not None
    assert completed.lease_owner is None


@pytest.mark.asyncio
async def test_repository_persists_failed_and_cancelled_terminals(repository) -> None:
    for run_id in ("failed-run", "cancelled-run"):
        await repository.create(
            RunRecord(id=run_id, question="问题", created_at=datetime.now(UTC))
        )
        await repository.claim(run_id, "worker-1", 60)

    failed = await repository.fail("failed-run", "worker-1", "安全错误摘要")
    cancelled = await repository.cancel(
        "cancelled-run", "worker-1", "运行被用户取消"
    )

    assert failed is not None
    assert failed.status == "failed"
    assert failed.error == "安全错误摘要"
    assert failed.termination_reason == "worker_error"
    assert cancelled is not None
    assert cancelled.status == "cancelled"
    assert cancelled.error == "运行被用户取消"
    assert cancelled.termination_reason == "cancelled"
    assert failed.lease_owner is None
    assert cancelled.lease_owner is None


@pytest.mark.asyncio
async def test_repository_reclaims_a_run_after_lease_expires(repository) -> None:
    now = datetime.now(UTC)
    await repository.create(
        RunRecord(
            id="run-1",
            question="问题",
            status="running",
            created_at=now - timedelta(minutes=5),
            started_at=now - timedelta(minutes=4),
            lease_owner="dead-worker",
            lease_expires_at=now - timedelta(minutes=1),
            attempt_count=1,
            version=1,
        )
    )

    reclaimed = await repository.claim("run-1", "worker-2", 60)

    assert reclaimed is not None
    assert reclaimed.lease_owner == "worker-2"
    assert reclaimed.attempt_count == 2
    assert reclaimed.version == 2


@pytest.mark.asyncio
async def test_repository_finds_only_stale_pending_and_expired_running_runs(
    repository,
) -> None:
    now = datetime.now(UTC)
    runs = (
        RunRecord(
            id="stale-pending",
            question="问题",
            created_at=now - timedelta(minutes=5),
        ),
        RunRecord(id="new-pending", question="问题", created_at=now),
        RunRecord(
            id="expired-running",
            question="问题",
            status="running",
            created_at=now - timedelta(minutes=5),
            lease_owner="dead-worker",
            lease_expires_at=now - timedelta(seconds=1),
        ),
        RunRecord(
            id="active-running",
            question="问题",
            status="running",
            created_at=now - timedelta(minutes=5),
            lease_owner="active-worker",
            lease_expires_at=now + timedelta(minutes=1),
        ),
    )
    for run in runs:
        await repository.create(run)

    recoverable = await repository.recoverable_before(
        now - timedelta(seconds=60), limit=100
    )

    assert {run.id for run in recoverable} == {
        "stale-pending",
        "expired-running",
    }
