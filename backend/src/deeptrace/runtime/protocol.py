"""Application-facing lifecycle contract implemented by each runtime mode."""

from collections.abc import AsyncIterator
from typing import Protocol

from deeptrace.runtime.models import RunMode, RunRecord, StoredEvent


class ResearchRuntime(Protocol):
    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    async def create(self, question: str, mode: RunMode) -> RunRecord: ...

    async def list(self) -> list[RunRecord]: ...

    async def get(self, run_id: str) -> RunRecord | None: ...

    async def cancel(self, run_id: str) -> RunRecord | None: ...

    def events(
        self, run_id: str, after_event_id: int = 0
    ) -> AsyncIterator[StoredEvent]: ...
