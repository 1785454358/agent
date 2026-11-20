"""Compatibility factory; all modes use the same delivery-first collector."""


def build_multi_agent_research_graph(
    topic_graph,
    *,
    max_researchers: int = 5,
    max_follow_ups: int = 1,
    max_follow_up_assignments: int = 2,
    checkpointer=None,
):
    from deeptrace.domain import ResearchMode
    from deeptrace.research.runtime import build_controller_research_graph

    return build_controller_research_graph(
        topic_graph,
        mode=ResearchMode.MULTI_AGENT,
        max_tasks=max_researchers,
        checkpointer=checkpointer,
    )
