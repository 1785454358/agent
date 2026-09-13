from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from deeptrace.domain import TRANSIENT_TOOL_ERROR_CODES, ToolRequest, ToolResult


class ExecutionConflictError(RuntimeError):
    pass


class ExecutionAbandonedError(RuntimeError):
    pass


class ClaimDisposition(StrEnum):
    OWNER = "owner"
    FOLLOWER = "follower"
    REPLAY = "replay"


class ExecutionClaim(BaseModel):
    """Serializable claim receipt that never exposes the internal Future."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    manager_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    call_id: str = Field(min_length=1)
    fingerprint: str = Field(min_length=1)
    generation: int = Field(ge=1)
    disposition: ClaimDisposition
    owner_token: str | None = None
    result: ToolResult | None = None

    @model_validator(mode="after")
    def validate_disposition_fields(self) -> ExecutionClaim:
        if self.disposition is ClaimDisposition.OWNER and self.owner_token is None:
            raise ValueError("owner claim requires owner_token")
        if self.disposition is not ClaimDisposition.OWNER and self.owner_token is not None:
            raise ValueError("non-owner claim cannot contain owner_token")
        if self.disposition is ClaimDisposition.REPLAY and self.result is None:
            raise ValueError("replay claim requires result")
        if self.disposition is not ClaimDisposition.REPLAY and self.result is not None:
            raise ValueError("non-replay claim cannot contain result")
        return self


class ToolExecutionStore(Protocol):
    async def claim(
        self,
        tenant_id: str,
        request: ToolRequest,
        *,
        mode: str | None = None,
        caller_id: str | None = None,
    ) -> ExecutionClaim: ...

    async def wait(self, claim: ExecutionClaim) -> ToolResult: ...

    async def complete(self, claim: ExecutionClaim, result: ToolResult) -> bool: ...

    async def abandon(self, claim: ExecutionClaim) -> bool: ...


@dataclass(frozen=True)
class _ExecutionIdentity:
    tenant_id: str
    run_id: str
    call_id: str


@dataclass
class _ExecutionRecord:
    request: ToolRequest
    fingerprint: str
    generation: int
    owner_token: str
    terminal_result: ToolResult | None = None
    abandoned: bool = False


_ABANDONED = object()
_SignalResult = ToolResult | object


class InMemoryToolExecutionStore:
    """Concurrency-safe execution ledger with replay and explicit reclaim."""

    def __init__(self) -> None:
        self._manager_id = uuid4().hex
        self._records: dict[_ExecutionIdentity, _ExecutionRecord] = {}
        self._signals: dict[
            tuple[_ExecutionIdentity, int], asyncio.Future[_SignalResult]
        ] = {}
        self._lock = asyncio.Lock()

    async def claim(
        self,
        tenant_id: str,
        request: ToolRequest,
        *,
        mode: str | None = None,
        caller_id: str | None = None,
    ) -> ExecutionClaim:
        tenant = _require_identifier("tenant_id", tenant_id)
        if not isinstance(request, ToolRequest):
            raise TypeError("request must be a ToolRequest")
        identity = _ExecutionIdentity(tenant, request.run_id, request.call_id)
        fingerprint = canonical_request_fingerprint(request)
        async with self._lock:
            record = self._records.get(identity)
            if record is None:
                return self._new_owner(identity, request, fingerprint, generation=1)
            if record.fingerprint != fingerprint:
                raise ExecutionConflictError(
                    "call_id was reused with a different fingerprint"
                )
            if record.terminal_result is not None:
                return self._claim(
                    identity,
                    record,
                    ClaimDisposition.REPLAY,
                    result=record.terminal_result.model_copy(deep=True),
                )
            if record.abandoned:
                return self._new_owner(
                    identity,
                    request,
                    fingerprint,
                    generation=record.generation + 1,
                )
            return self._claim(identity, record, ClaimDisposition.FOLLOWER)

    async def wait(self, claim: ExecutionClaim) -> ToolResult:
        self._require_claim(claim)
        if claim.disposition is not ClaimDisposition.FOLLOWER:
            raise ValueError("only follower claims can wait")
        identity = _identity_from_claim(claim)
        async with self._lock:
            signal = self._signals.get((identity, claim.generation))
            if signal is None:
                raise KeyError("execution generation is not available")
        outcome = await asyncio.shield(signal)
        if outcome is _ABANDONED:
            raise ExecutionAbandonedError("execution was abandoned")
        if not isinstance(outcome, ToolResult):
            raise RuntimeError("execution completed with an invalid result")
        return outcome.model_copy(deep=True)

    async def complete(self, claim: ExecutionClaim, result: ToolResult) -> bool:
        self._require_claim(claim)
        if claim.disposition is not ClaimDisposition.OWNER:
            raise ValueError("only owner claims can complete execution")
        if not isinstance(result, ToolResult):
            raise TypeError("result must be a ToolResult")
        identity = _identity_from_claim(claim)
        async with self._lock:
            record = self._records.get(identity)
            if not self._owns(record, claim):
                return False
            self._validate_result(record.request, result)
            if (
                not result.ok
                and result.error_code in TRANSIENT_TOOL_ERROR_CODES
            ):
                # Transient failures stay recoverable: a node-level retry may
                # claim the call again and truly re-execute the provider.
                record.abandoned = True
                signal = self._signals[(identity, record.generation)]
                if not signal.done():
                    signal.set_result(_ABANDONED)
                return True
            record.terminal_result = result.model_copy(deep=True)
            signal = self._signals[(identity, record.generation)]
            if not signal.done():
                signal.set_result(record.terminal_result)
            return True

    async def abandon(self, claim: ExecutionClaim) -> bool:
        self._require_claim(claim)
        if claim.disposition is not ClaimDisposition.OWNER:
            raise ValueError("only owner claims can abandon execution")
        identity = _identity_from_claim(claim)
        async with self._lock:
            record = self._records.get(identity)
            if not self._owns(record, claim):
                return False
            record.abandoned = True
            signal = self._signals[(identity, record.generation)]
            if not signal.done():
                signal.set_result(_ABANDONED)
            return True

    def _new_owner(
        self,
        identity: _ExecutionIdentity,
        request: ToolRequest,
        fingerprint: str,
        *,
        generation: int,
    ) -> ExecutionClaim:
        record = _ExecutionRecord(
            request=request.model_copy(deep=True),
            fingerprint=fingerprint,
            generation=generation,
            owner_token=uuid4().hex,
        )
        self._records[identity] = record
        self._signals[(identity, generation)] = (
            asyncio.get_running_loop().create_future()
        )
        return self._claim(identity, record, ClaimDisposition.OWNER)

    def _claim(
        self,
        identity: _ExecutionIdentity,
        record: _ExecutionRecord,
        disposition: ClaimDisposition,
        *,
        result: ToolResult | None = None,
    ) -> ExecutionClaim:
        return ExecutionClaim(
            manager_id=self._manager_id,
            tenant_id=identity.tenant_id,
            run_id=identity.run_id,
            call_id=identity.call_id,
            fingerprint=record.fingerprint,
            generation=record.generation,
            disposition=disposition,
            owner_token=(
                record.owner_token
                if disposition is ClaimDisposition.OWNER
                else None
            ),
            result=result,
        )

    def _require_claim(self, claim: object) -> None:
        if not isinstance(claim, ExecutionClaim):
            raise TypeError("claim must be an ExecutionClaim")
        if claim.manager_id != self._manager_id:
            raise ValueError("claim belongs to a different execution store")

    @staticmethod
    def _owns(
        record: _ExecutionRecord | None, claim: ExecutionClaim
    ) -> bool:
        return bool(
            record is not None
            and record.generation == claim.generation
            and record.owner_token == claim.owner_token
            and record.terminal_result is None
            and not record.abandoned
        )

    @staticmethod
    def _validate_result(request: ToolRequest, result: ToolResult) -> None:
        expected = (
            request.request_id,
            request.run_id,
            request.thread_id,
            request.call_id,
            request.tool,
        )
        actual = (
            result.request_id,
            result.run_id,
            result.thread_id,
            result.call_id,
            result.tool,
        )
        if actual != expected:
            raise ValueError("result correlation does not match claimed request")


def canonical_request_fingerprint(request: ToolRequest) -> str:
    if not isinstance(request, ToolRequest):
        raise TypeError("request must be a ToolRequest")
    payload = json.dumps(
        {
            "request_id": request.request_id,
            "thread_id": request.thread_id,
            "tool": request.tool.value,
            "arguments": request.arguments,
        },
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _identity_from_claim(claim: ExecutionClaim) -> _ExecutionIdentity:
    return _ExecutionIdentity(claim.tenant_id, claim.run_id, claim.call_id)


def _require_identifier(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()
