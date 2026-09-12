from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from langchain_core.runnables import RunnableConfig

from deeptrace.domain import ResearchMode


class ResearchStrategyGraph(Protocol):
    async def ainvoke(
        self,
        input: dict[str, Any],
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]: ...


@dataclass(frozen=True)
class StrategyRegistration:
    name: ResearchMode
    graph: ResearchStrategyGraph


class StrategyRegistry:
    def __init__(self) -> None:
        self._items: dict[ResearchMode, StrategyRegistration] = {}

    def register(self, registration: StrategyRegistration) -> None:
        if not isinstance(registration.name, ResearchMode):
            raise TypeError("registration name must be a ResearchMode")
        if registration.name in self._items:
            raise ValueError(
                f"mode already registered: {registration.name.value}"
            )
        self._items[registration.name] = registration

    def resolve(self, name: ResearchMode) -> StrategyRegistration:
        if not isinstance(name, ResearchMode):
            raise TypeError("mode name must be a ResearchMode")
        try:
            return self._items[name]
        except KeyError as exc:
            raise KeyError(f"mode is not registered: {name.value}") from exc

    def modes(self) -> tuple[ResearchMode, ...]:
        return tuple(self._items)
