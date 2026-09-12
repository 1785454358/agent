"""Research strategy subgraphs: Workflow, Plan-and-Execute, Multi-Agent."""

from deeptrace.strategies.multi_agent import build_multi_agent_research_graph
from deeptrace.strategies.plan_execute import build_plan_execute_research_graph
from deeptrace.strategies.topic import build_research_topic_graph
from deeptrace.strategies.workflow import build_workflow_research_graph

__all__ = [
    "build_multi_agent_research_graph",
    "build_plan_execute_research_graph",
    "build_research_topic_graph",
    "build_workflow_research_graph",
]
