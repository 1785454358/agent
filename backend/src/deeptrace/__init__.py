"""DeepResearch: one top-level LangGraph runtime graph, three research modes.

All research traffic (API, Worker, CLI) runs through
``deeptrace.application`` — the top-level runtime graph with the Workflow,
Plan-and-Execute and Multi-Agent strategy subgraphs.
"""

from deeptrace.models import AgentResult, RunEvent

__all__ = ["AgentResult", "RunEvent"]
