"""Compatibility factory; all modes use the same delivery-first collector."""


def build_workflow_research_graph(
    topic_graph, *, query_limit: int = 3, checkpointer=None
):
    from deeptrace.domain import ResearchMode
    from deeptrace.research.runtime import build_controller_research_graph

    return build_controller_research_graph(
        topic_graph,
        mode=ResearchMode.WORKFLOW,
        max_tasks=query_limit,
        checkpointer=checkpointer,
    )
