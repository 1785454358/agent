"""ResearchPilot agents with three independent research modes."""

from deeptrace.basic.agent import ResearchAgent
from deeptrace.basic.service import build_basic_agent
from deeptrace.deep.agent import DeepResearchAgent
from deeptrace.deep.service import build_deep_agent
from deeptrace.models import AgentResult
from deeptrace.multi_agent.agent import SupervisorResearchAgent
from deeptrace.multi_agent.service import build_multi_agent


def build_real_agent(settings, on_event=None, *, mode="basic"):
    """Route to the appropriate mode-specific agent builder."""
    if mode == "deep":
        return build_deep_agent(settings, on_event)
    if mode == "multi_agent":
        return build_multi_agent(settings, on_event)
    if mode == "basic":
        return build_basic_agent(settings, on_event)
    raise ValueError("研究模式必须为 basic、deep 或 multi_agent")


__all__ = [
    "AgentResult",
    "DeepResearchAgent",
    "ResearchAgent",
    "SupervisorResearchAgent",
    "build_basic_agent",
    "build_deep_agent",
    "build_multi_agent",
    "build_real_agent",
]
