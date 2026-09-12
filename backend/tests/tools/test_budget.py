from __future__ import annotations

import asyncio

import pytest
from pydantic import ValidationError

from deeptrace.domain.execution import BudgetSnapshot, ResearchMode
from deeptrace.tools.budget import (
    BudgetScopeKey,
    BudgetUnits,
    InMemoryBudgetManager,
)


def _scope_limits() -> dict[BudgetScopeKey, BudgetUnits]:
    run = BudgetScopeKey.for_run("run-1")
    workflow = BudgetScopeKey.for_mode("run-1", ResearchMode.WORKFLOW)
    researcher_a = BudgetScopeKey.for_agent(
        "run-1", ResearchMode.WORKFLOW, "researcher-a"
    )
    researcher_b = BudgetScopeKey.for_agent(
        "run-1", ResearchMode.WORKFLOW, "researcher-b"
    )
    planner = BudgetScopeKey.for_mode("run-1", ResearchMode.PLAN_EXECUTE)
    executor = BudgetScopeKey.for_agent(
        "run-1", ResearchMode.PLAN_EXECUTE, "executor"
    )
    return {
        researcher_b: BudgetUnits(tool_calls=4),
        workflow: BudgetUnits(tool_calls=5),
        run: BudgetUnits(tool_calls=6),
        executor: BudgetUnits(tool_calls=4),
        planner: BudgetUnits(tool_calls=4),
        researcher_a: BudgetUnits(tool_calls=4),
    }


def test_scope_keys_require_canonical_modes_and_valid_hierarchy() -> None:
    with pytest.raises(ValidationError):
        BudgetScopeKey.for_mode("run-1", "workflow")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        BudgetScopeKey(run_id="run-1", agent_id="researcher-a")
    with pytest.raises(ValidationError):
        BudgetScopeKey(run_id="run-1", mode=ResearchMode.WORKFLOW, agent_id="")


@pytest.mark.asyncio
async def test_concurrent_reservations_respect_child_and_ancestor_ceilings() -> None:
    manager = InMemoryBudgetManager(_scope_limits())
    researcher_a = BudgetScopeKey.for_agent(
        "run-1", ResearchMode.WORKFLOW, "researcher-a"
    )
    researcher_b = BudgetScopeKey.for_agent(
        "run-1", ResearchMode.WORKFLOW, "researcher-b"
    )
    executor = BudgetScopeKey.for_agent(
        "run-1", ResearchMode.PLAN_EXECUTE, "executor"
    )

    a_results = await asyncio.gather(
        *(manager.reserve(researcher_a, BudgetUnits(tool_calls=1)) for _ in range(20))
    )
    b_results = await asyncio.gather(
        *(manager.reserve(researcher_b, BudgetUnits(tool_calls=1)) for _ in range(20))
    )
    executor_results = await asyncio.gather(
        *(manager.reserve(executor, BudgetUnits(tool_calls=1)) for _ in range(20))
    )

    assert sum(item is not None for item in a_results) == 4
    assert sum(item is not None for item in b_results) == 1
    assert sum(item is not None for item in executor_results) == 1

    snapshot = await manager.snapshot()
    assert snapshot.for_scope(BudgetScopeKey.for_run("run-1")).reserved.tool_calls == 6
    assert snapshot.for_scope(
        BudgetScopeKey.for_mode("run-1", ResearchMode.WORKFLOW)
    ).reserved.tool_calls == 5
    assert snapshot.for_scope(researcher_a).reserved.tool_calls == 4
    assert snapshot.for_scope(researcher_b).reserved.tool_calls == 1


@pytest.mark.asyncio
async def test_sibling_agents_and_modes_race_shared_ancestors_atomically() -> None:
    run = BudgetScopeKey.for_run("run-race")
    modes = (
        ResearchMode.WORKFLOW,
        ResearchMode.PLAN_EXECUTE,
    )
    agents = tuple(
        BudgetScopeKey.for_agent("run-race", mode, agent_id)
        for mode in modes
        for agent_id in ("agent-a", "agent-b")
    )
    limits: dict[BudgetScopeKey, BudgetUnits] = {
        run: BudgetUnits(network_requests=5)
    }
    for mode in modes:
        limits[BudgetScopeKey.for_mode("run-race", mode)] = BudgetUnits(
            network_requests=3
        )
    for agent in agents:
        limits[agent] = BudgetUnits(network_requests=2)
    manager = InMemoryBudgetManager(limits)
    start = asyncio.Event()

    async def reserve_after_barrier(scope: BudgetScopeKey):
        await start.wait()
        return await manager.reserve(scope, BudgetUnits(network_requests=1))

    tasks = [
        asyncio.create_task(reserve_after_barrier(agent))
        for agent in agents
        for _ in range(10)
    ]
    await asyncio.sleep(0)
    start.set()
    results = await asyncio.gather(*tasks)

    accepted = [receipt for receipt in results if receipt is not None]
    assert len(accepted) == 5
    snapshot = await manager.snapshot()
    assert snapshot.for_scope(run).reserved.network_requests == 5
    mode_totals: list[int] = []
    for mode in modes:
        mode_scope = BudgetScopeKey.for_mode("run-race", mode)
        mode_receipts = [
            receipt for receipt in accepted if receipt.scope.mode is mode
        ]
        mode_total = len(mode_receipts)
        mode_totals.append(mode_total)
        assert mode_total <= 3
        assert (
            snapshot.for_scope(mode_scope).reserved.network_requests
            == mode_total
        )
        agent_total = sum(
            snapshot.for_scope(agent).reserved.network_requests
            for agent in agents
            if agent.mode is mode
        )
        assert agent_total == mode_total
    assert sorted(mode_totals) == [2, 3]


@pytest.mark.asyncio
async def test_rejected_reservation_does_not_change_any_scope_counter() -> None:
    run = BudgetScopeKey.for_run("run-1")
    mode = BudgetScopeKey.for_mode("run-1", ResearchMode.WORKFLOW)
    agent = BudgetScopeKey.for_agent(
        "run-1", ResearchMode.WORKFLOW, "researcher"
    )
    manager = InMemoryBudgetManager(
        {
            run: BudgetUnits(network_requests=1),
            mode: BudgetUnits(network_requests=1),
            agent: BudgetUnits(network_requests=1),
        }
    )

    rejected = await manager.reserve(agent, BudgetUnits(network_requests=2))

    assert rejected is None
    snapshot = await manager.snapshot()
    for scope in (run, mode, agent):
        item = snapshot.for_scope(scope)
        assert item.used == BudgetUnits()
        assert item.reserved == BudgetUnits()


@pytest.mark.asyncio
async def test_commit_charges_actual_attempt_and_releases_unused_pages() -> None:
    run = BudgetScopeKey.for_run("run-1")
    mode = BudgetScopeKey.for_mode("run-1", ResearchMode.WORKFLOW)
    agent = BudgetScopeKey.for_agent(
        "run-1", ResearchMode.WORKFLOW, "researcher"
    )
    limit = BudgetUnits(tool_calls=3, network_requests=3, fetched_pages=5)
    manager = InMemoryBudgetManager({run: limit, mode: limit, agent: limit})
    reservation = await manager.reserve(
        agent,
        BudgetUnits(tool_calls=1, network_requests=1, fetched_pages=3),
    )
    assert reservation is not None

    changed = await manager.commit(
        reservation,
        BudgetUnits(tool_calls=1, network_requests=1, fetched_pages=1),
    )

    assert changed is True
    snapshot = await manager.snapshot()
    for scope in (run, mode, agent):
        item = snapshot.for_scope(scope)
        assert item.used == BudgetUnits(
            tool_calls=1, network_requests=1, fetched_pages=1
        )
        assert item.reserved == BudgetUnits()


@pytest.mark.asyncio
async def test_commit_and_release_are_terminal_and_idempotent() -> None:
    run = BudgetScopeKey.for_run("run-1")
    limit = BudgetUnits(tool_calls=2, network_requests=2)
    manager = InMemoryBudgetManager({run: limit})
    committed = await manager.reserve(
        run, BudgetUnits(tool_calls=1, network_requests=1)
    )
    released = await manager.reserve(
        run, BudgetUnits(tool_calls=1, network_requests=1)
    )
    assert committed is not None
    assert released is not None

    assert await manager.commit(
        committed, BudgetUnits(tool_calls=1, network_requests=1)
    )
    assert not await manager.commit(
        committed, BudgetUnits(tool_calls=1, network_requests=1)
    )
    assert not await manager.release(committed)

    assert await manager.release(released)
    assert not await manager.release(released)
    assert not await manager.commit(released, BudgetUnits(tool_calls=1))

    item = (await manager.snapshot()).for_scope(run)
    assert item.used == BudgetUnits(tool_calls=1, network_requests=1)
    assert item.reserved == BudgetUnits()


@pytest.mark.asyncio
async def test_foreign_manager_cannot_accept_an_otherwise_equal_receipt() -> None:
    run = BudgetScopeKey.for_run("run-1")
    limit = {run: BudgetUnits(tool_calls=1)}
    first_manager = InMemoryBudgetManager(limit)
    second_manager = InMemoryBudgetManager(limit)
    first_receipt = await first_manager.reserve(run, BudgetUnits(tool_calls=1))
    second_receipt = await second_manager.reserve(run, BudgetUnits(tool_calls=1))
    assert first_receipt is not None
    assert second_receipt is not None
    assert first_receipt.reservation_id == second_receipt.reservation_id

    with pytest.raises(ValueError, match="different budget manager"):
        await second_manager.commit(first_receipt, BudgetUnits(tool_calls=1))

    second_snapshot = (await second_manager.snapshot()).for_scope(run)
    assert second_snapshot.used == BudgetUnits()
    assert second_snapshot.reserved == BudgetUnits(tool_calls=1)


@pytest.mark.asyncio
async def test_invalid_commit_preserves_the_live_reservation() -> None:
    run = BudgetScopeKey.for_run("run-1")
    manager = InMemoryBudgetManager({run: BudgetUnits(fetched_pages=3)})
    reservation = await manager.reserve(run, BudgetUnits(fetched_pages=2))
    assert reservation is not None

    with pytest.raises(ValueError, match="cannot exceed reserved units"):
        await manager.commit(reservation, BudgetUnits(fetched_pages=3))

    item = (await manager.snapshot()).for_scope(run)
    assert item.used == BudgetUnits()
    assert item.reserved == BudgetUnits(fetched_pages=2)


@pytest.mark.asyncio
async def test_snapshot_order_is_deterministic_and_contains_only_contract_data() -> None:
    limits = _scope_limits()
    manager = InMemoryBudgetManager(dict(reversed(tuple(limits.items()))))

    snapshot = await manager.snapshot()

    assert [item.scope.path for item in snapshot.scopes] == [
        "run-1",
        "run-1/plan_execute",
        "run-1/plan_execute/executor",
        "run-1/workflow",
        "run-1/workflow/researcher-a",
        "run-1/workflow/researcher-b",
    ]
    assert "lock" not in snapshot.model_dump_json().lower()


@pytest.mark.asyncio
async def test_snapshot_order_does_not_depend_on_ambiguous_display_paths() -> None:
    nested_run = BudgetScopeKey.for_run("shared/workflow")
    root_run = BudgetScopeKey.for_run("shared")
    mode = BudgetScopeKey.for_mode("shared", ResearchMode.WORKFLOW)
    limits = {
        nested_run: BudgetUnits(tool_calls=1),
        root_run: BudgetUnits(tool_calls=1),
        mode: BudgetUnits(tool_calls=1),
    }
    forward = InMemoryBudgetManager(limits)
    reverse = InMemoryBudgetManager(dict(reversed(tuple(limits.items()))))

    forward_scopes = tuple(item.scope for item in (await forward.snapshot()).scopes)
    reverse_scopes = tuple(item.scope for item in (await reverse.snapshot()).scopes)

    assert forward_scopes == reverse_scopes


@pytest.mark.asyncio
async def test_scope_snapshot_projects_committed_usage_to_execution_contract() -> None:
    run = BudgetScopeKey.for_run("run-1")
    limit = BudgetUnits(model_calls=4, tool_calls=6, network_requests=5)
    manager = InMemoryBudgetManager({run: limit})
    reservation = await manager.reserve(
        run, BudgetUnits(model_calls=2, tool_calls=1, network_requests=1)
    )
    assert reservation is not None
    await manager.commit(
        reservation, BudgetUnits(model_calls=1, tool_calls=1, network_requests=1)
    )

    execution_snapshot = (
        (await manager.snapshot()).for_scope(run).to_execution_snapshot()
    )

    assert execution_snapshot == BudgetSnapshot(
        max_model_calls=4,
        max_tool_calls=6,
        max_network_requests=5,
        used_model_calls=1,
        used_tool_calls=1,
        used_network_requests=1,
    )
