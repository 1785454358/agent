from deeptrace.basic.graph import build_research_graph


def test_graph_is_basic_pipeline() -> None:
    graph = build_research_graph().get_graph()

    assert set(graph.nodes) == {
        "__start__",
        "plan",
        "parallel_research",
        "writer",
        "__end__",
    }
    assert {(edge.source, edge.target) for edge in graph.edges} == {
        ("__start__", "plan"),
        ("plan", "parallel_research"),
        ("parallel_research", "writer"),
        ("writer", "__end__"),
    }
