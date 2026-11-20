import pytest

from deeptrace.persistence.database import create_session_factory
from deeptrace.persistence.orm import Base


@pytest.mark.asyncio
async def test_snapshot_compare_and_swap_preserves_newer_usage(tmp_path):
    from deeptrace.persistence.model_budget import SqlAlchemyModelBudgetStore

    engine, sessions = create_session_factory(
        f"sqlite+aiosqlite:///{tmp_path / 'budgets.db'}"
    )
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        store = SqlAlchemyModelBudgetStore(sessions)
        assert await store.load("run-1") is None
        first = await store.save("run-1", {"used_calls": 1}, None)
        second = await store.save("run-1", {"used_calls": 2}, first)
        with pytest.raises(RuntimeError, match="budget_revision_conflict"):
            await store.save("run-1", {"used_calls": 0}, first)
        with pytest.raises(RuntimeError, match="budget_revision_conflict"):
            await store.save("run-1", {"used_calls": 0}, None)
        reopened = SqlAlchemyModelBudgetStore(sessions)
        assert await reopened.load("run-1") == (second, {"used_calls": 2})
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_gateway_restores_budget_after_sql_engine_reopen(tmp_path):
    from harness.test_durable_model_budget import Provider, call, gateway

    from deeptrace.persistence.model_budget import SqlAlchemyModelBudgetStore

    dsn = f"sqlite+aiosqlite:///{tmp_path / 'restart.db'}"
    provider, tick = Provider(), [100.0]
    engine, sessions = create_session_factory(dsn)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        await call(gateway(provider, SqlAlchemyModelBudgetStore(sessions), tick))
    finally:
        await engine.dispose()
    engine, sessions = create_session_factory(dsn)
    try:
        resumed = gateway(provider, SqlAlchemyModelBudgetStore(sessions), tick)
        with pytest.raises(RuntimeError, match="budget_exhausted:model_calls"):
            await call(resumed)
        assert resumed.usage_payload()["total_tokens"] == 82
        assert provider.calls == 1
    finally:
        await engine.dispose()
