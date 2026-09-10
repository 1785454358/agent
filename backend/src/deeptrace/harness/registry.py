from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from langchain_core.runnables import RunnableConfig

from deeptrace.domain import ResearchProfile


class ProfileGraph(Protocol):
    async def ainvoke(
        self,
        input: dict[str, Any],
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]: ...


@dataclass(frozen=True)
class ProfileRegistration:
    name: ResearchProfile
    graph: ProfileGraph


class ProfileRegistry:
    def __init__(self) -> None:
        self._items: dict[ResearchProfile, ProfileRegistration] = {}

    def register(self, registration: ProfileRegistration) -> None:
        if not isinstance(registration.name, ResearchProfile):
            raise TypeError("registration name must be a ResearchProfile")
        if registration.name in self._items:
            raise ValueError(
                f"profile already registered: {registration.name.value}"
            )
        self._items[registration.name] = registration

    def resolve(self, name: ResearchProfile) -> ProfileRegistration:
        if not isinstance(name, ResearchProfile):
            raise TypeError("profile name must be a ResearchProfile")
        try:
            return self._items[name]
        except KeyError as exc:
            raise KeyError(f"profile is not registered: {name.value}") from exc

    def profiles(self) -> tuple[ResearchProfile, ...]:
        return tuple(self._items)
