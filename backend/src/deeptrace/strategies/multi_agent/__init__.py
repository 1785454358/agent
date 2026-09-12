"""Multi-Agent research strategy: supervisor → Send(researchers) → evaluate."""

from deeptrace.strategies.multi_agent.graph import build_multi_agent_research_graph
from deeptrace.strategies.multi_agent.models import SupervisorEvaluation
from deeptrace.strategies.multi_agent.state import (
    MultiAgentState,
    ResearcherBranchState,
)

__all__ = [
    "MultiAgentState",
    "ResearcherBranchState",
    "SupervisorEvaluation",
    "build_multi_agent_research_graph",
]
