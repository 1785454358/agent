"""Supervisor Multi-Agent research mode."""

from deeptrace.multi_agent.agent import SupervisorResearchAgent
from deeptrace.multi_agent.graph import build_multi_agent_graph
from deeptrace.multi_agent.models import (
    AssignmentDraft,
    ResearchAssignment,
    ResearcherResult,
    SupervisorDecision,
)
from deeptrace.multi_agent.service import build_multi_agent

__all__ = [
    "AssignmentDraft",
    "ResearchAssignment",
    "ResearcherResult",
    "SupervisorDecision",
    "SupervisorResearchAgent",
    "build_multi_agent",
    "build_multi_agent_graph",
]
