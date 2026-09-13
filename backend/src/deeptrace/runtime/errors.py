"""Runtime-level lifecycle errors."""

from __future__ import annotations


class ThreadBusyError(RuntimeError):
    """The conversation thread already has an active run."""

    def __init__(self, thread_id: str) -> None:
        super().__init__(f"会话 {thread_id} 已有进行中的研究，请稍后再试")
        self.thread_id = thread_id
