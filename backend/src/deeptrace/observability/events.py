"""Structured event collection and aggregate metrics for harness runs."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class HarnessEventRecorder:
    """EventSink that records bounded, sanitized run events and aggregates metrics.

    Events carry identifiers and stable codes only — never page bodies or
    provider exception text (the gateway already sanitizes payloads).
    """

    run_id: str | None = None
    events: list[dict[str, Any]] = field(default_factory=list)
    on_sync_event: Any = None
    _lock: threading.Lock = field(default_factory=threading.Lock)

    async def emit(self, event_type: str, payload: dict[str, Any]) -> None:
        record = {
            "event_type": event_type,
            "ts": datetime.now(UTC).isoformat(),
            "payload": dict(payload),
        }
        with self._lock:
            self.events.append(record)
            if len(self.events) > 2_000:
                del self.events[:1_000]
        hook = self.on_sync_event
        if hook is not None:
            try:
                hook(event_type, dict(payload))
            except Exception:
                return

    def metrics(self) -> dict[str, Any]:
        tool_started = 0
        tool_completed = 0
        tool_failed = 0
        cached = 0
        duration_ms = 0
        with self._lock:
            for event in self.events:
                if event["event_type"] == "tool.started":
                    tool_started += 1
                elif event["event_type"] == "tool.completed":
                    tool_completed += 1
                    duration_ms += int(event["payload"].get("duration_ms") or 0)
                    if event["payload"].get("cached"):
                        cached += 1
                    if not event["payload"].get("ok", True):
                        tool_failed += 1
        return {
            "tool_started": tool_started,
            "tool_completed": tool_completed,
            "tool_failed": tool_failed,
            "tool_cached": cached,
            "tool_duration_ms_total": duration_ms,
            "event_count": len(self.events),
        }
