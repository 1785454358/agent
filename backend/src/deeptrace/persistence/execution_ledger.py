"""SQL-backed tool execution ledger with replay-safe claims."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from deeptrace.domain import ToolRequest, ToolResult
from deeptrace.tools.execution_store import (
    canonical_request_fingerprint,
    ClaimDisposition,
    ExecutionAbandonedError,
    ExecutionClaim,
    ExecutionConflictError,
)
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from deeptrace.persistence.orm import ToolExecutionRow
from deeptrace.tools.budget import BudgetUnits


def _now() -> datetime:
    return datetime.now(UTC)


class SqlAlchemyToolExecutionStore:
    """Claim/complete/replay semantics over SQL; followers poll for the result.

    ``wait`` is a bounded poll: distributed followers re-check the ledger until
    the owner commits or the claim is abandoned.
    """

    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        *,
        poll_interval_seconds: float = 0.02,
        max_polls: int = 250,
    ) -> None:
        self._sessions = sessions
        self._poll_interval_seconds = poll_interval_seconds
        self._max_polls = max_polls
        self._manager_id = uuid.uuid4().hex

    async def claim(
        self,
        tenant_id: str,
        request: ToolRequest,
        *,
        mode: str | None = None,
        caller_id: str | None = None,
    ) -> ExecutionClaim:
        fingerprint = canonical_request_fingerprint(request)
        async with self._sessions() as session:
            row = (
                await session.execute(
                    select(ToolExecutionRow).where(
                        ToolExecutionRow.tenant_id == tenant_id,
                        ToolExecutionRow.run_id == request.run_id,
                        ToolExecutionRow.call_id == request.call_id,
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                token = uuid.uuid4().hex
                session.add(
                    ToolExecutionRow(
                        tenant_id=tenant_id,
                        run_id=request.run_id,
                        call_id=request.call_id,
                        fingerprint=fingerprint,
                        mode=mode,
                        caller_id=caller_id,
                        status="running",
                        generation=1,
                        owner_token=token,
                        created_at=_now(),
                        updated_at=_now(),
                    )
                )
                try:
                    await session.commit()
                except IntegrityError:
                    # Another process inserted the same identity after our
                    # initial read. Re-read it and become a follower/replay.
                    await session.rollback()
                    row = (
                        await session.execute(
                            select(ToolExecutionRow).where(
                                ToolExecutionRow.tenant_id == tenant_id,
                                ToolExecutionRow.run_id == request.run_id,
                                ToolExecutionRow.call_id == request.call_id,
                            )
                        )
                    ).scalar_one()
                else:
                    return ExecutionClaim(
                        manager_id=self._manager_id,
                        tenant_id=tenant_id,
                        run_id=request.run_id,
                        call_id=request.call_id,
                        fingerprint=fingerprint,
                        disposition=ClaimDisposition.OWNER,
                        owner_token=token,
                        generation=1,
                    )
            if row.fingerprint != fingerprint:
                raise ExecutionConflictError(
                    "call_id was reused with a different fingerprint"
                )
            if row.status in {"recoverable", "abandoned"}:
                token = uuid.uuid4().hex
                next_generation = row.generation + 1
                changed = await session.execute(
                    update(ToolExecutionRow)
                    .where(
                        ToolExecutionRow.id == row.id,
                        ToolExecutionRow.status == row.status,
                        ToolExecutionRow.generation == row.generation,
                    )
                    .values(
                        status="running",
                        owner_token=token,
                        generation=next_generation,
                        updated_at=_now(),
                    )
                )
                await session.commit()
                if changed.rowcount == 1:
                    return ExecutionClaim(
                        manager_id=self._manager_id,
                        tenant_id=tenant_id,
                        run_id=request.run_id,
                        call_id=request.call_id,
                        fingerprint=fingerprint,
                        disposition=ClaimDisposition.OWNER,
                        owner_token=token,
                        generation=next_generation,
                    )
                row = (
                    await session.execute(
                        select(ToolExecutionRow).where(
                            ToolExecutionRow.tenant_id == tenant_id,
                            ToolExecutionRow.run_id == request.run_id,
                            ToolExecutionRow.call_id == request.call_id,
                        )
                    )
                ).scalar_one()
            if row.result_json is not None:
                result = ToolResult.model_validate(row.result_json)
                return ExecutionClaim(
                    manager_id=self._manager_id,
                    tenant_id=tenant_id,
                    run_id=request.run_id,
                    call_id=request.call_id,
                    fingerprint=fingerprint,
                    disposition=ClaimDisposition.REPLAY,
                    result=result,
                    generation=row.generation,
                )
            return ExecutionClaim(
                manager_id=self._manager_id,
                tenant_id=tenant_id,
                run_id=request.run_id,
                call_id=request.call_id,
                fingerprint=fingerprint,
                disposition=ClaimDisposition.FOLLOWER,
                generation=row.generation,
            )

    async def wait(self, claim: ExecutionClaim) -> ToolResult:
        import asyncio

        for _ in range(self._max_polls):
            async with self._sessions() as session:
                row = (
                    await session.execute(
                        select(ToolExecutionRow).where(
                            ToolExecutionRow.tenant_id == claim.tenant_id,
                            ToolExecutionRow.run_id == claim.run_id,
                            ToolExecutionRow.call_id == claim.call_id,
                        )
                    )
                ).scalar_one_or_none()
            if row is None:
                raise ExecutionAbandonedError("execution record disappeared")
            if row.generation != claim.generation:
                raise ExecutionAbandonedError("execution generation was replaced")
            if row.status == "recoverable":
                raise ExecutionAbandonedError("execution can be retried")
            if row.result_json is not None:
                return ToolResult.model_validate(row.result_json)
            if row.status == "abandoned":
                raise ExecutionAbandonedError("owner abandoned the execution")
            await asyncio.sleep(self._poll_interval_seconds)
        raise ExecutionAbandonedError("owner did not complete in time")

    async def complete(
        self,
        claim: ExecutionClaim,
        result: ToolResult,
        *,
        consumed: BudgetUnits | None = None,
    ) -> bool:
        units = consumed or BudgetUnits()
        if not isinstance(units, BudgetUnits):
            raise TypeError("consumed must be BudgetUnits")
        async with self._sessions() as session:
            row = (
                await session.execute(
                    select(ToolExecutionRow).where(
                        ToolExecutionRow.tenant_id == claim.tenant_id,
                        ToolExecutionRow.run_id == claim.run_id,
                        ToolExecutionRow.call_id == claim.call_id,
                    )
                )
            ).scalar_one_or_none()
            if (
                row is None
                or row.status != "running"
                or row.owner_token != claim.owner_token
            ):
                return False
            if row.generation != claim.generation:
                return False
            row.consumed_tool_calls += units.tool_calls
            row.consumed_network_requests += units.network_requests
            row.consumed_fetched_pages += units.fetched_pages
            if not result.ok and result.retryable:
                # Transient failures stay recoverable for node-level retries.
                row.status = "recoverable"
                row.owner_token = None
                row.updated_at = _now()
                await session.commit()
                return True
            row.result_json = result.model_dump(mode="json")
            row.status = "completed"
            row.owner_token = None
            row.updated_at = _now()
            await session.commit()
            return True

    async def abandon(self, claim: ExecutionClaim) -> bool:
        async with self._sessions() as session:
            row = (
                await session.execute(
                    select(ToolExecutionRow).where(
                        ToolExecutionRow.tenant_id == claim.tenant_id,
                        ToolExecutionRow.run_id == claim.run_id,
                        ToolExecutionRow.call_id == claim.call_id,
                    )
                )
            ).scalar_one_or_none()
            if row is None or row.owner_token != claim.owner_token:
                return False
            row.status = "abandoned"
            row.owner_token = None
            row.updated_at = _now()
            await session.commit()
            return True


    async def tool_usage_for_run(self, run_id: str) -> dict[tuple[str, str], BudgetUnits]:
        """Reconstruct consumed budget units from durable ledger counters.

        Used to seed budget counters after a crash so a resumed run cannot
        exceed its original allowance.
        """
        from collections import defaultdict

        usage: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0, 0])
        async with self._sessions() as session:
            rows = (
                (
                    await session.execute(
                        select(ToolExecutionRow).where(
                            ToolExecutionRow.run_id == run_id,
                        )
                    )
                )
                .scalars()
                .all()
            )
        for row in rows:
            if row.mode is None or row.caller_id is None:
                continue
            counts = usage[(row.mode, row.caller_id)]
            counts[0] += row.consumed_tool_calls
            counts[1] += row.consumed_network_requests
            counts[2] += row.consumed_fetched_pages
        return {
            key: BudgetUnits(
                tool_calls=value[0],
                network_requests=value[1],
                fetched_pages=value[2],
            )
            for key, value in usage.items()
        }
