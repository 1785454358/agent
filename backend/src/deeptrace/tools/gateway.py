from __future__ import annotations

import asyncio
import hashlib
from time import perf_counter
from typing import Any, Protocol

from pydantic import BaseModel, ValidationError

from deeptrace.domain import ToolName, ToolRequest, ToolResult
from deeptrace.tools.budget import (
    BudgetManager,
    BudgetScopeKey,
    BudgetUnits,
)
from deeptrace.tools.cache import (
    SingleflightExecutionError,
    ToolCacheKey,
    ToolExecutionCoordinator,
    page_cache_key,
    search_cache_key,
)
from deeptrace.tools.contracts import (
    CachePolicy,
    ToolAdapterResult,
    ToolCapability,
    ToolSpec,
)
from deeptrace.tools.evidence_store import EvidenceStore
from deeptrace.tools.execution_store import (
    ClaimDisposition,
    ExecutionAbandonedError,
    ToolExecutionStore,
)
from deeptrace.tools.policy import (
    ToolAllowlistPolicy,
    ToolCaller,
    UrlAuthorization,
    UrlSecurityPolicy,
)
from deeptrace.tools.registry import ToolRegistry


class EventSink(Protocol):
    async def emit(self, event_type: str, payload: dict[str, Any]) -> None: ...


class AgentToolGateway:
    """Policy and reliability boundary for every runtime tool execution."""

    def __init__(
        self,
        *,
        registry: ToolRegistry,
        allowlist: ToolAllowlistPolicy,
        security: UrlSecurityPolicy,
        budgets: BudgetManager,
        executions: ToolExecutionStore,
        cache: ToolExecutionCoordinator,
        evidence_store: EvidenceStore,
        event_sink: EventSink,
    ) -> None:
        self._registry = registry
        self._allowlist = allowlist
        self._security = security
        self._budgets = budgets
        self._executions = executions
        self._cache = cache
        self._evidence_store = evidence_store
        self._event_sink = event_sink

    async def execute(
        self,
        *,
        tenant_id: str,
        caller: ToolCaller,
        request: ToolRequest,
        authorization: UrlAuthorization | None = None,
        provider_id: str = "default",
        refresh: bool = False,
    ) -> ToolResult:
        if not isinstance(request, ToolRequest):
            raise TypeError("request must be a ToolRequest")
        if not isinstance(caller, ToolCaller):
            raise TypeError("caller must be a ToolCaller")
        tenant = _require_text("tenant_id", tenant_id)
        provider = _require_text("provider_id", provider_id)

        try:
            spec = self._allowlist.resolve(self._registry, caller, request.tool)
        except KeyError:
            return _failure(request, "tool_not_registered")
        except PermissionError:
            return _failure(request, "tool_not_allowed")

        try:
            arguments = spec.argument_model.model_validate(request.arguments)
        except ValidationError:
            return _failure(request, "invalid_arguments")

        try:
            secured = self._security.validate(
                request.tool,
                arguments.model_dump(mode="json"),
                authorization,
            )
            arguments = spec.argument_model.model_validate(secured)
        except PermissionError:
            return _failure(request, "url_not_authorized")
        except (TypeError, ValueError, ValidationError):
            return _failure(request, "unsafe_arguments")

        claim = await self._executions.claim(
            tenant,
            request,
            mode=None if caller.mode is None else caller.mode.value,
            caller_id=caller.caller_id,
        )
        if claim.disposition is ClaimDisposition.REPLAY:
            assert claim.result is not None
            return claim.result.model_copy(update={"replayed": True}, deep=True)
        if claim.disposition is ClaimDisposition.FOLLOWER:
            try:
                result = await self._executions.wait(claim)
            except ExecutionAbandonedError:
                return _failure(request, "execution_abandoned")
            return result.model_copy(update={"replayed": True}, deep=True)

        scope = _budget_scope(request, caller)
        requested_units = _budget_units(spec.capability)
        reservation = await self._budgets.reserve(scope, requested_units)
        if reservation is None:
            result = _failure(request, "budget_exhausted")
            await self._executions.complete(claim, result, consumed=BudgetUnits())
            return result

        started_at = perf_counter()
        try:
            cache_key = _cache_key(tenant, spec, arguments, provider)
            if cache_key is None or refresh:
                # Refresh still participates in singleflight when caching is enabled.
                result = (
                    await self._cache.get_or_execute(
                        cache_key,
                        lambda: self._invoke(
                            tenant, caller, request, spec, arguments
                        ),
                        refresh=True,
                    )
                    if cache_key is not None
                    else await self._invoke(
                        tenant, caller, request, spec, arguments
                    )
                )
            else:
                result = await self._cache.get_or_execute(
                    cache_key,
                    lambda: self._invoke(
                        tenant, caller, request, spec, arguments
                    ),
                )

            result = _rebind(result, request)
            if result.cached:
                await self._budgets.release(reservation)
                consumed = BudgetUnits()
            else:
                await self._budgets.commit(reservation, requested_units)
                consumed = requested_units
                await self._emit_completed(
                    caller, result, requested_units, started_at
                )
            await self._executions.complete(claim, result, consumed=consumed)
            return result
        except asyncio.CancelledError:
            await self._budgets.release(reservation)
            await self._emit_event(
                "tool.cancelled",
                _event_payload(caller, request),
            )
            await self._executions.abandon(claim)
            raise
        except SingleflightExecutionError:
            await self._budgets.release(reservation)
            result = _failure(request, "shared_execution_failed")
            await self._executions.complete(claim, result, consumed=BudgetUnits())
            return result
        except Exception:
            # Infrastructure failures are sanitized at the gateway boundary.
            await self._budgets.release(reservation)
            result = _failure(request, "tool_internal_error")
            await self._executions.complete(claim, result, consumed=BudgetUnits())
            return result

    async def _invoke(
        self,
        tenant_id: str,
        caller: ToolCaller,
        request: ToolRequest,
        spec: ToolSpec,
        arguments: BaseModel,
    ) -> ToolResult:
        await self._emit_event(
            "tool.started",
            _event_payload(caller, request),
        )
        try:
            async with asyncio.timeout(spec.timeout_seconds):
                adapter_result = await spec.handler(arguments)
            if not isinstance(adapter_result, ToolAdapterResult):
                return _failure(request, "invalid_adapter_result")
            return await self._project_result(
                tenant_id, request, spec, adapter_result
            )
        except TimeoutError:
            return _failure(request, "provider_timeout")
        except asyncio.CancelledError:
            raise
        except Exception:
            return _failure(request, "provider_error")

    async def _project_result(
        self,
        tenant_id: str,
        request: ToolRequest,
        spec: ToolSpec,
        adapter_result: ToolAdapterResult,
    ) -> ToolResult:
        if not adapter_result.ok:
            assert adapter_result.error_code is not None
            return _failure(request, adapter_result.error_code)
        evidence_ids: list[str] = []
        data_ref = adapter_result.data_ref
        if adapter_result.evidence is not None:
            if not spec.stores_evidence:
                return _failure(request, "unexpected_evidence")
            evidence = await self._evidence_store.ingest(
                tenant_id, adapter_result.evidence
            )
            evidence_ids.append(evidence.id)
            data_ref = f"evidence://{evidence.id}/body"
        elif spec.stores_evidence:
            return _failure(request, "missing_evidence")

        return ToolResult(
            **_correlation(request),
            ok=True,
            preview=adapter_result.preview[: spec.preview_limit],
            data_ref=data_ref,
            evidence_ids=evidence_ids,
        )

    async def _emit_completed(
        self,
        caller: ToolCaller,
        result: ToolResult,
        budget_delta: BudgetUnits,
        started_at: float,
    ) -> None:
        payload = _event_payload(caller, result)
        payload.update(
            {
                "ok": result.ok,
                "error_code": result.error_code,
                "cached": result.cached,
                "replayed": result.replayed,
                "budget_delta": budget_delta.model_dump(mode="json"),
                "duration_ms": max(0, round((perf_counter() - started_at) * 1000)),
            }
        )
        await self._emit_event("tool.completed", payload)

    async def _emit_event(
        self, event_type: str, payload: dict[str, Any]
    ) -> None:
        try:
            await self._event_sink.emit(event_type, payload)
        except Exception:
            # Telemetry is deliberately isolated from the execution outcome.
            return


def _budget_scope(request: ToolRequest, caller: ToolCaller) -> BudgetScopeKey:
    if caller.mode is None:
        return BudgetScopeKey.for_run(request.run_id)
    return BudgetScopeKey.for_agent(request.run_id, caller.mode, caller.caller_id)


def _budget_units(capability: ToolCapability) -> BudgetUnits:
    network = capability in {
        ToolCapability.WEB_SEARCH,
        ToolCapability.PAGE_FETCH,
    }
    return BudgetUnits(
        tool_calls=1,
        network_requests=int(network),
        fetched_pages=int(capability is ToolCapability.PAGE_FETCH),
    )


def _cache_key(
    tenant_id: str,
    spec: ToolSpec,
    arguments: BaseModel,
    provider_id: str,
) -> ToolCacheKey | None:
    if spec.cache_policy is CachePolicy.NONE:
        return None
    values = arguments.model_dump(mode="json")
    if spec.name is ToolName.SEARCH_WEB:
        query = values.pop("query")
        base_key = search_cache_key(query, provider_id, values)
    elif spec.name is ToolName.FETCH_PAGE:
        url = values["url"]
        version = values.get("content_version")
        base_key = page_cache_key(url, content_version=version)
    else:
        return None
    digest = hashlib.sha256(
        f"{tenant_id}\0{base_key.namespace}\0{base_key.digest}".encode("utf-8")
    ).hexdigest()
    return ToolCacheKey(namespace=base_key.namespace, digest=digest)


def _event_payload(caller: ToolCaller, value: ToolRequest | ToolResult) -> dict[str, Any]:
    return {
        "request_id": value.request_id,
        "run_id": value.run_id,
        "thread_id": value.thread_id,
        "call_id": value.call_id,
        "tool": value.tool.value,
        "caller_id": caller.caller_id,
        "mode": None if caller.mode is None else caller.mode.value,
    }


def _correlation(request: ToolRequest) -> dict[str, Any]:
    return {
        "request_id": request.request_id,
        "run_id": request.run_id,
        "thread_id": request.thread_id,
        "call_id": request.call_id,
        "tool": request.tool,
    }


def _failure(request: ToolRequest, code: str) -> ToolResult:
    return ToolResult(**_correlation(request), ok=False, error_code=code)


def _rebind(result: ToolResult, request: ToolRequest) -> ToolResult:
    return result.model_copy(update=_correlation(request), deep=True)


def _require_text(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()
