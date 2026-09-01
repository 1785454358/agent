from deeptrace.agent.planner import build_fallback_plan, normalize_question


def test_normalize_question_collapses_whitespace() -> None:
    assert normalize_question("  2024年AI Agent领域有哪 些进展？  ") == (
        "2024年AI Agent领域有哪些进展？"
    )


def test_fallback_plan_is_single_task_and_preserves_question() -> None:
    plan = build_fallback_plan("2024 年 Agent 进展", min_sources=2)

    assert len(plan.tasks) == 1
    assert plan.tasks[0].question == plan.normalized_query
    assert plan.tasks[0].min_sources == 2
