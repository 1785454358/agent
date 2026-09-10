from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum
import inspect
import math
from typing import Any

from pydantic import BaseModel

from deeptrace.domain import ToolName
from deeptrace.domain.tools import MAX_TOOL_PREVIEW_LENGTH


class ToolCapability(StrEnum):
    WEB_SEARCH = "web_search"
    PAGE_FETCH = "page_fetch"
    MEMORY_READ = "memory_read"
    MEMORY_WRITE = "memory_write"
    EVIDENCE_READ = "evidence_read"


class CachePolicy(StrEnum):
    NONE = "none"
    SUCCESS = "success"


ToolHandler = Callable[[BaseModel], Awaitable[Any]]


@dataclass(frozen=True)
class ToolSpec:
    name: ToolName
    argument_model: type[BaseModel]
    handler: ToolHandler
    capability: ToolCapability
    cache_policy: CachePolicy
    timeout_seconds: float
    preview_limit: int
    stores_evidence: bool

    def __post_init__(self) -> None:
        if not isinstance(self.name, ToolName):
            raise TypeError("spec name must be a ToolName")
        if not (
            isinstance(self.argument_model, type)
            and issubclass(self.argument_model, BaseModel)
        ):
            raise TypeError("argument_model must be a Pydantic BaseModel type")
        if not callable(self.handler) or not (
            inspect.iscoroutinefunction(self.handler)
            or inspect.iscoroutinefunction(getattr(self.handler, "__call__", None))
        ):
            raise TypeError("handler must be async")
        if not isinstance(self.capability, ToolCapability):
            raise TypeError("capability must be a ToolCapability")
        if not isinstance(self.cache_policy, CachePolicy):
            raise TypeError("cache_policy must be a CachePolicy")
        if not isinstance(self.timeout_seconds, (int, float)) or isinstance(
            self.timeout_seconds, bool
        ):
            raise TypeError("timeout_seconds must be numeric")
        if not math.isfinite(self.timeout_seconds):
            raise ValueError("timeout_seconds must be finite")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")
        if not isinstance(self.preview_limit, int) or isinstance(self.preview_limit, bool):
            raise TypeError("preview_limit must be an int")
        if self.preview_limit < 0:
            raise ValueError("preview_limit cannot be negative")
        if self.preview_limit > MAX_TOOL_PREVIEW_LENGTH:
            raise ValueError(
                f"preview_limit cannot exceed {MAX_TOOL_PREVIEW_LENGTH}"
            )
        if not isinstance(self.stores_evidence, bool):
            raise TypeError("stores_evidence must be a bool")
