"""Public tool runtime and legacy search entry points."""

from deeptrace.tools.adapters import (
    FetchPageArguments,
    SearchMemoryArguments,
    SearchWebArguments,
    build_research_tool_registry,
)
from deeptrace.tools.contracts import ToolAdapterResult
from deeptrace.tools.gateway import AgentToolGateway
from deeptrace.tools.search import ToolContext, search_web

__all__ = [
    "AgentToolGateway",
    "FetchPageArguments",
    "SearchMemoryArguments",
    "SearchWebArguments",
    "ToolAdapterResult",
    "ToolContext",
    "build_research_tool_registry",
    "search_web",
]
