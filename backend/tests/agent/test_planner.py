from deeptrace.agent.planner import (
    build_fallback_plan,
    detect_query_language,
    normalize_question,
    parse_planner_draft,
)


def test_query_language_is_deterministic() -> None:
    assert detect_query_language("2024年 AI Agent 有哪些进展？") == "zh-CN"
    assert detect_query_language("What changed in AI agents in 2024?") == "en"


def test_normalize_question_collapses_whitespace() -> None:
    assert normalize_question("  2024年AI Agent领域有哪 些进展？  ") == (
        "2024年AI Agent领域有哪些进展？"
    )


def test_fallback_plan_is_single_task_and_preserves_question() -> None:
    plan = build_fallback_plan("2024 年 Agent 进展", min_sources=2)

    assert len(plan.tasks) == 1
    assert plan.tasks[0].question == plan.normalized_query
    assert plan.tasks[0].min_sources == 2


def test_planner_parses_fenced_json_without_provider_specific_parameters() -> None:
    draft = parse_planner_draft(
        """```json
        {
          "objective": "总结进展",
          "language": "zh-CN",
          "tasks": [
            {"title": "技术", "question": "技术进展？", "planned_queries": ["技术进展"], "expected_topics": ["技术"]},
            {"title": "应用", "question": "应用进展？", "planned_queries": ["应用进展"], "expected_topics": ["应用"]}
          ],
          "report_outline": ["技术", "应用"]
        }
        ```"""
    )

    assert len(draft.tasks) == 2
    assert draft.tasks[0].title == "技术"
