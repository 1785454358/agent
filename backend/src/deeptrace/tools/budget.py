from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import ClassVar, Mapping, Self
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from deeptrace.domain.execution import BudgetSnapshot, ResearchProfile


class BudgetUnits(BaseModel):
    """Immutable counters used for both ceilings and accounting deltas."""

    model_config = ConfigDict(frozen=True, strict=True)

    model_calls: int = Field(default=0, ge=0)
    tool_calls: int = Field(default=0, ge=0)
    network_requests: int = Field(default=0, ge=0)
    fetched_pages: int = Field(default=0, ge=0)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    rounds: int = Field(default=0, ge=0)

    _COUNTERS: ClassVar[tuple[str, ...]] = (
        "model_calls",
        "tool_calls",
        "network_requests",
        "fetched_pages",
        "input_tokens",
        "output_tokens",
        "rounds",
    )

    def plus(self, other: Self) -> Self:
        self._require_units(other)
        return type(self)(
            **{
                counter: getattr(self, counter) + getattr(other, counter)
                for counter in self._COUNTERS
            }
        )

    def minus(self, other: Self) -> Self:
        self._require_units(other)
        if not other.fits_within(self):
            raise ValueError("budget subtraction cannot produce negative units")
        return type(self)(
            **{
                counter: getattr(self, counter) - getattr(other, counter)
                for counter in self._COUNTERS
            }
        )

    def fits_within(self, ceiling: Self) -> bool:
        self._require_units(ceiling)
        return all(
            getattr(self, counter) <= getattr(ceiling, counter)
            for counter in self._COUNTERS
        )

    def is_empty(self) -> bool:
        return all(getattr(self, counter) == 0 for counter in self._COUNTERS)

    @staticmethod
    def _require_units(value: object) -> None:
        if not isinstance(value, BudgetUnits):
            raise TypeError("budget value must be BudgetUnits")


class BudgetScopeKey(BaseModel):
    """Serializable identity for a Run, Profile, or Agent budget scope."""

    model_config = ConfigDict(frozen=True, strict=True)

    run_id: str = Field(min_length=1)
    profile: ResearchProfile | None = None
    agent_id: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_hierarchy(self) -> BudgetScopeKey:
        if self.agent_id is not None and self.profile is None:
            raise ValueError("agent scope requires a profile")
        return self

    @classmethod
    def for_run(cls, run_id: str) -> BudgetScopeKey:
        return cls(run_id=run_id)

    @classmethod
    def for_profile(
        cls, run_id: str, profile: ResearchProfile
    ) -> BudgetScopeKey:
        return cls(run_id=run_id, profile=profile)

    @classmethod
    def for_agent(
        cls,
        run_id: str,
        profile: ResearchProfile,
        agent_id: str,
    ) -> BudgetScopeKey:
        return cls(run_id=run_id, profile=profile, agent_id=agent_id)

    @property
    def path(self) -> str:
        parts = [self.run_id]
        if self.profile is not None:
            parts.append(self.profile.value)
        if self.agent_id is not None:
            parts.append(self.agent_id)
        return "/".join(parts)

    def lineage(self) -> tuple[BudgetScopeKey, ...]:
        scopes = [type(self).for_run(self.run_id)]
        if self.profile is not None:
            scopes.append(type(self).for_profile(self.run_id, self.profile))
        if self.agent_id is not None:
            scopes.append(
                type(self).for_agent(self.run_id, self.profile, self.agent_id)
            )
        return tuple(scopes)


class BudgetReservation(BaseModel):
    """Immutable receipt for capacity provisionally held across a lineage."""

    model_config = ConfigDict(frozen=True, strict=True)

    manager_id: str = Field(min_length=1)
    reservation_id: str = Field(min_length=1)
    scope: BudgetScopeKey
    requested: BudgetUnits


class BudgetScopeSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True)

    scope: BudgetScopeKey
    limit: BudgetUnits
    used: BudgetUnits
    reserved: BudgetUnits

    def to_execution_snapshot(self) -> BudgetSnapshot:
        """Project committed counters onto the graph-facing budget contract."""
        return BudgetSnapshot(
            max_model_calls=self.limit.model_calls,
            max_tool_calls=self.limit.tool_calls,
            max_network_requests=self.limit.network_requests,
            used_model_calls=self.used.model_calls,
            used_tool_calls=self.used.tool_calls,
            used_network_requests=self.used.network_requests,
        )


class BudgetManagerSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True)

    scopes: tuple[BudgetScopeSnapshot, ...]

    def for_scope(self, scope: BudgetScopeKey) -> BudgetScopeSnapshot:
        if not isinstance(scope, BudgetScopeKey):
            raise TypeError("scope must be a BudgetScopeKey")
        for item in self.scopes:
            if item.scope == scope:
                return item
        raise KeyError(f"budget scope is not configured: {scope.path}")


@dataclass
class _ScopeCounters:
    used: BudgetUnits
    reserved: BudgetUnits


@dataclass
class _ReservationState:
    receipt: BudgetReservation
    terminal: bool = False


class InMemoryBudgetManager:
    """Concurrency-safe runtime manager for hierarchical budget reservations."""

    def __init__(self, limits: Mapping[BudgetScopeKey, BudgetUnits]) -> None:
        if not limits:
            raise ValueError("at least one budget scope must be configured")
        self._limits = dict(limits)
        self._validate_limits()
        self._counters = {
            scope: _ScopeCounters(used=BudgetUnits(), reserved=BudgetUnits())
            for scope in self._limits
        }
        self._reservations: dict[str, _ReservationState] = {}
        self._manager_id = uuid4().hex
        self._next_reservation = 1
        self._lock = asyncio.Lock()

    async def reserve(
        self, scope: BudgetScopeKey, requested: BudgetUnits
    ) -> BudgetReservation | None:
        self._require_scope(scope)
        self._require_units(requested)
        if requested.is_empty():
            raise ValueError("reservation must request at least one unit")
        lineage = scope.lineage()
        async with self._lock:
            for ancestor in lineage:
                counters = self._counters[ancestor]
                claimed = counters.used.plus(counters.reserved).plus(requested)
                if not claimed.fits_within(self._limits[ancestor]):
                    return None

            receipt = BudgetReservation(
                manager_id=self._manager_id,
                reservation_id=f"reservation-{self._next_reservation:08d}",
                scope=scope,
                requested=requested,
            )
            self._next_reservation += 1
            for ancestor in lineage:
                counters = self._counters[ancestor]
                counters.reserved = counters.reserved.plus(requested)
            self._reservations[receipt.reservation_id] = _ReservationState(receipt)
            return receipt

    async def commit(
        self, reservation: BudgetReservation, used: BudgetUnits
    ) -> bool:
        self._require_reservation(reservation)
        self._require_units(used)
        async with self._lock:
            state = self._reservation_state(reservation)
            if state.terminal:
                return False
            if not used.fits_within(reservation.requested):
                raise ValueError("committed units cannot exceed reserved units")
            for scope in reservation.scope.lineage():
                counters = self._counters[scope]
                counters.reserved = counters.reserved.minus(reservation.requested)
                counters.used = counters.used.plus(used)
            state.terminal = True
            return True

    async def release(self, reservation: BudgetReservation) -> bool:
        self._require_reservation(reservation)
        async with self._lock:
            state = self._reservation_state(reservation)
            if state.terminal:
                return False
            for scope in reservation.scope.lineage():
                counters = self._counters[scope]
                counters.reserved = counters.reserved.minus(reservation.requested)
            state.terminal = True
            return True

    async def snapshot(self) -> BudgetManagerSnapshot:
        async with self._lock:
            return BudgetManagerSnapshot(
                scopes=tuple(
                    BudgetScopeSnapshot(
                        scope=scope,
                        limit=self._limits[scope],
                        used=self._counters[scope].used,
                        reserved=self._counters[scope].reserved,
                    )
                    for scope in sorted(
                        self._limits,
                        key=lambda item: (
                            item.run_id,
                            item.profile.value if item.profile is not None else "",
                            item.agent_id or "",
                        ),
                    )
                )
            )

    def _validate_limits(self) -> None:
        for scope, limit in self._limits.items():
            self._require_scope(scope)
            self._require_units(limit)
        for scope in self._limits:
            missing = [
                ancestor.path
                for ancestor in scope.lineage()
                if ancestor not in self._limits
            ]
            if missing:
                raise ValueError(
                    f"budget scope {scope.path} is missing ancestors: {', '.join(missing)}"
                )

    def _reservation_state(self, receipt: BudgetReservation) -> _ReservationState:
        if receipt.manager_id != self._manager_id:
            raise ValueError("reservation belongs to a different budget manager")
        try:
            state = self._reservations[receipt.reservation_id]
        except KeyError as exc:
            raise KeyError(
                f"unknown budget reservation: {receipt.reservation_id}"
            ) from exc
        if state.receipt != receipt:
            raise ValueError("reservation receipt does not match the issued reservation")
        return state

    def _require_scope(self, scope: object) -> None:
        if not isinstance(scope, BudgetScopeKey):
            raise TypeError("scope must be a BudgetScopeKey")
        if scope not in self._limits:
            raise KeyError(f"budget scope is not configured: {scope.path}")

    @staticmethod
    def _require_units(units: object) -> None:
        if not isinstance(units, BudgetUnits):
            raise TypeError("budget value must be BudgetUnits")

    @staticmethod
    def _require_reservation(reservation: object) -> None:
        if not isinstance(reservation, BudgetReservation):
            raise TypeError("reservation must be a BudgetReservation")
