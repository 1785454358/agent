from __future__ import annotations

import asyncio

import pytest

from deeptrace.application.assembly import _SeededBudgets
from deeptrace.domain import ResearchMode
from deeptrace.tools.budget import BudgetScopeKey, BudgetUnits, InMemoryBudgetManager


@pytest.mark.asyncio
async def test_concurrent_first_reservations_wait_for_one_complete_seed() -> None:
    run = BudgetScopeKey.for_run("run-resumed")
    mode = BudgetScopeKey.for_mode("run-resumed", ResearchMode.WORKFLOW)
    agent = BudgetScopeKey.for_agent(
        "run-resumed", ResearchMode.WORKFLOW, "researcher"
    )
    limit = BudgetUnits(tool_calls=2, network_requests=2)
    inner = InMemoryBudgetManager({run: limit, mode: limit, agent: limit})
    seed_started = asyncio.Event()
    release_seed = asyncio.Event()
    calls = 0

    async def seed():
        nonlocal calls
        calls += 1
        seed_started.set()
        await release_seed.wait()
        return {
            ("workflow", "researcher"): BudgetUnits(
                tool_calls=1, network_requests=1
            )
        }

    budgets = _SeededBudgets(inner, seed, "run-resumed")
    requested = BudgetUnits(tool_calls=1, network_requests=1)
    first = asyncio.create_task(budgets.reserve(agent, requested))
    await seed_started.wait()
    second = asyncio.create_task(budgets.reserve(agent, requested))
    await asyncio.sleep(0)
    release_seed.set()

    receipts = await asyncio.gather(first, second)

    assert calls == 1
    assert sum(receipt is not None for receipt in receipts) == 1
    snapshot = await inner.snapshot()
    for scope in (run, mode, agent):
        assert snapshot.for_scope(scope).used == requested
        assert snapshot.for_scope(scope).reserved == requested
