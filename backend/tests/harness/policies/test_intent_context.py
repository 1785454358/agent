from deeptrace.domain import ConversationIntent, ResponseMode
from deeptrace.harness.policies.context import (
    HARD_MESSAGE_LIMIT,
    SOFT_MESSAGE_LIMIT,
    plan_context_window,
)
from deeptrace.harness.policies.intent import classify_intent


def test_explicit_special_intents_win_over_research() -> None:
    assert (
        classify_intent("记住我喜欢简洁的回答", prior_evidence=False)
        is ConversationIntent.MEMORY_UPDATE
    )
    assert (
        classify_intent("以后都用中文回答，记住这一点", prior_evidence=False)
        is ConversationIntent.MEMORY_UPDATE
    )
    assert (
        classify_intent("切换到 plan_execute 模式", prior_evidence=True)
        is ConversationIntent.SWITCH_MODE
    )
    assert (
        classify_intent("生成报告", prior_evidence=True)
        is ConversationIntent.REPORT_REQUEST
    )


def test_follow_ups_use_existing_evidence_without_new_research() -> None:
    for question in (
        "总结一下上面的要点",
        "继续解释一下",
        "为什么是这个结论？",
        "上面提到的 checkpoint 存在哪里",
    ):
        assert (
            classify_intent(question, prior_evidence=True)
            is ConversationIntent.CONVERSATION
        )
    assert (
        classify_intent("总结一下上面的要点", prior_evidence=False)
        is ConversationIntent.RESEARCH
    )


def test_incremental_research_requires_prior_evidence() -> None:
    assert (
        classify_intent("再查一下 2026 年的最新进展", prior_evidence=True)
        is ConversationIntent.INCREMENTAL_RESEARCH
    )
    assert (
        classify_intent("补充一下分布式部署的资料", prior_evidence=True)
        is ConversationIntent.INCREMENTAL_RESEARCH
    )
    assert (
        classify_intent("补充一下分布式部署的资料", prior_evidence=False)
        is ConversationIntent.RESEARCH
    )


def test_new_questions_research() -> None:
    assert (
        classify_intent("LangGraph 的 checkpoint 存在哪里", prior_evidence=False)
        is ConversationIntent.RESEARCH
    )
    assert (
        classify_intent("对比一下三种研究模式的成本", prior_evidence=False)
        is ConversationIntent.RESEARCH
    )


def test_intent_always_selects_a_report_response_mode_for_report_requests() -> None:
    from deeptrace.harness.policies.intent import response_mode_for_intent

    assert (
        response_mode_for_intent(ConversationIntent.REPORT_REQUEST, "生成报告")
        is ResponseMode.REPORT
    )
    assert (
        response_mode_for_intent(ConversationIntent.MEMORY_UPDATE, "记住偏好")
        is ResponseMode.ANSWER
    )
    assert (
        response_mode_for_intent(ConversationIntent.CONVERSATION, "继续解释一下")
        is ResponseMode.ANSWER
    )
    assert (
        response_mode_for_intent(ConversationIntent.CONVERSATION, "总结一下要点")
        is ResponseMode.BRIEF
    )


def test_context_window_keeps_recent_messages_and_marks_overflow() -> None:
    from langchain_core.messages import HumanMessage

    messages = [
        HumanMessage(content=f"m{index}", id=f"id-{index}")
        for index in range(SOFT_MESSAGE_LIMIT + 5)
    ]

    kept, overflow = plan_context_window(messages)

    assert len(kept) == SOFT_MESSAGE_LIMIT
    assert [message.id for message in kept] == [
        f"id-{index}" for index in range(5, SOFT_MESSAGE_LIMIT + 5)
    ]
    assert [message.id for message in overflow] == [f"id-{index}" for index in range(5)]

    small = messages[:3]
    kept, overflow = plan_context_window(small)
    assert (kept, overflow) == (small, [])


def test_hard_limit_bounds_even_recent_messages() -> None:
    from langchain_core.messages import HumanMessage

    messages = [
        HumanMessage(content=f"m{index}", id=f"id-{index}")
        for index in range(HARD_MESSAGE_LIMIT + 10)
    ]

    kept, overflow = plan_context_window(messages)

    assert len(kept) == HARD_MESSAGE_LIMIT
    assert len(overflow) == 10
