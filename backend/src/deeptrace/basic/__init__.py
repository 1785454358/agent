"""Basic research mode: flat one-pass pipeline with LangGraph."""

from deeptrace.basic.agent import ResearchAgent
from deeptrace.basic.service import build_basic_agent

__all__ = ["ResearchAgent", "build_basic_agent"]
