"""Best-effort semantic graph events; observers cannot change research decisions."""
from __future__ import annotations

import logging
from typing import Any

from deeptrace.harness.context import HarnessContext


async def emit_progress(context: HarnessContext, event_type: str, **payload: Any) -> None:
    try:
        await context.event_sink.emit(event_type, payload)
    except Exception:
        logging.getLogger(__name__).warning("Research progress observer failed", exc_info=True)
