"""Compatibility factory; all modes use the same delivery-first collector."""


def build_plan_execute_research_graph(
    topic_graph,
    *,
    max_tasks: int = 6,
    max_replans: int = 2,
    max_replan_tasks: int = 2,
    checkpointer=None,
):
    from deeptrace.domain import ResearchMode
    from deeptrace.research.runtime import build_controller_research_graph

    return build_controller_research_graph(
        topic_graph,
        mode=ResearchMode.PLAN_EXECUTE,
        max_tasks=max_tasks,
        checkpointer=checkpointer,
    )
