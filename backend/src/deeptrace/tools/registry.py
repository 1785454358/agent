from __future__ import annotations

from deeptrace.domain import ToolName
from deeptrace.domain.tools import CustomToolName
from deeptrace.tools.contracts import ToolCapability, ToolSpec

_REQUIRED_CAPABILITIES: dict[ToolName, ToolCapability] = {
    ToolName.SEARCH_WEB: ToolCapability.WEB_SEARCH,
    ToolName.FETCH_PAGE: ToolCapability.PAGE_FETCH,
    ToolName.SEARCH_MEMORY: ToolCapability.MEMORY_READ,
    ToolName.READ_EVIDENCE: ToolCapability.EVIDENCE_READ,
}


class ToolRegistry:
    def __init__(self) -> None:
        self._specs: dict[ToolName | CustomToolName, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if not isinstance(spec.name, (ToolName, CustomToolName)):
            raise TypeError("spec name must be a ToolName or CustomToolName")
        required_capability = _REQUIRED_CAPABILITIES.get(spec.name)
        if required_capability is not None and spec.capability is not required_capability:
            raise ValueError(
                f"{spec.name.value} requires capability {required_capability.value}"
            )
        if spec.name in self._specs:
            raise ValueError(f"tool is already registered: {spec.name.value}")
        self._specs[spec.name] = spec

    def resolve(self, name: ToolName | CustomToolName) -> ToolSpec:
        if not isinstance(name, (ToolName, CustomToolName)):
            raise TypeError("tool name must be a ToolName or CustomToolName")
        try:
            return self._specs[name]
        except KeyError as exc:
            raise KeyError(f"tool is not registered: {name.value}") from exc

    def names(self) -> tuple[ToolName | CustomToolName, ...]:
        return tuple(self._specs)
