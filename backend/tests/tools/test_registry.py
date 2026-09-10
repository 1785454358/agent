from __future__ import annotations

from dataclasses import FrozenInstanceError
import math

import pytest
from pydantic import BaseModel, Field

from deeptrace.domain import ToolName
from deeptrace.harness.checkpoint import create_harness_checkpoint_serializer
from deeptrace.tools.contracts import CachePolicy, ToolCapability, ToolSpec
from deeptrace.tools.registry import ToolRegistry


class SearchArguments(BaseModel):
    query: str = Field(min_length=1)


async def _handler(arguments: BaseModel) -> dict[str, str]:
    return {"query": str(arguments)}


def _sync_handler(arguments: BaseModel) -> dict[str, str]:
    return {"query": str(arguments)}


def _spec(
    name: ToolName = ToolName.SEARCH_WEB,
    *,
    capability: ToolCapability = ToolCapability.WEB_SEARCH,
) -> ToolSpec:
    return ToolSpec(
        name=name,
        argument_model=SearchArguments,
        handler=_handler,
        capability=capability,
        cache_policy=CachePolicy.SUCCESS,
        timeout_seconds=10.0,
        preview_limit=500,
        stores_evidence=True,
    )


def test_registry_resolves_only_canonical_tool_names() -> None:
    registry = ToolRegistry()
    spec = _spec()

    registry.register(spec)

    assert registry.resolve(ToolName.SEARCH_WEB) is spec
    assert registry.names() == (ToolName.SEARCH_WEB,)
    with pytest.raises(KeyError, match="tool is not registered"):
        registry.resolve(ToolName.FETCH_PAGE)
    with pytest.raises(TypeError, match="tool name must be a ToolName"):
        registry.resolve("search_web")  # type: ignore[arg-type]


def test_registry_rejects_duplicates_and_noncanonical_specs() -> None:
    registry = ToolRegistry()
    registry.register(_spec())

    with pytest.raises(ValueError, match="already registered"):
        registry.register(_spec())
    with pytest.raises(TypeError, match="spec name must be a ToolName"):
        _spec("search_web")  # type: ignore[arg-type]


def test_registry_rejects_capability_spoofing_for_atomic_tools() -> None:
    registry = ToolRegistry()

    with pytest.raises(ValueError, match="requires capability web_search"):
        registry.register(
            _spec(
                ToolName.SEARCH_WEB,
                capability=ToolCapability.EVIDENCE_READ,
            )
        )


def test_tool_spec_is_immutable_and_runtime_only() -> None:
    spec = _spec()

    with pytest.raises(FrozenInstanceError):
        spec.timeout_seconds = 1.0  # type: ignore[misc]

    serializer = create_harness_checkpoint_serializer()
    with pytest.raises(TypeError):
        serializer.dumps_typed(spec)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("capability", "web_search", "capability must be a ToolCapability"),
        ("cache_policy", "success", "cache_policy must be a CachePolicy"),
        ("timeout_seconds", 0, "timeout_seconds must be greater than zero"),
        ("timeout_seconds", math.nan, "timeout_seconds must be finite"),
        ("preview_limit", -1, "preview_limit cannot be negative"),
        ("preview_limit", 4_001, "preview_limit cannot exceed 4000"),
        ("preview_limit", 1.5, "preview_limit must be an int"),
        ("handler", _sync_handler, "handler must be async"),
    ],
)
def test_tool_spec_rejects_invalid_runtime_configuration(
    field: str, value: object, message: str
) -> None:
    values = {
        "name": ToolName.SEARCH_WEB,
        "argument_model": SearchArguments,
        "handler": _handler,
        "capability": ToolCapability.WEB_SEARCH,
        "cache_policy": CachePolicy.SUCCESS,
        "timeout_seconds": 10.0,
        "preview_limit": 500,
        "stores_evidence": True,
    }
    values[field] = value

    with pytest.raises((TypeError, ValueError), match=message):
        ToolSpec(**values)  # type: ignore[arg-type]
