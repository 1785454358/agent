import pytest
from pydantic import ValidationError

from deeptrace.models import TokenUsage, UsageBreakdown
from deeptrace.multi_agent.models import (
    RESEARCHER_MODEL_TOOLS,
    AssignmentDraft,
    ResearchAssignment,
    ResearcherResult,
    SupervisorDecision,
)
from deeptrace.observability import format_role_usage


def test_dispatch_requires_assignments_and_finish_forbids_them():
    with pytest.raises(ValidationError):
        SupervisorDecision(action="dispatch", rationale="需要分工", assignments=[])
    with pytest.raises(ValidationError):
        SupervisorDecision(
            action="finish",
            rationale="资料充分",
            assignments=[
                AssignmentDraft(
                    objective="研究技术",
                    required_outputs=["代表性进展"],
                    excluded_scope=[],
                    source_guidance=["官方来源"],
                )
            ],
        )


def test_finish_sufficiency_and_gaps_are_consistent():
    with pytest.raises(ValidationError):
        SupervisorDecision(
            action="finish",
            rationale="仍有关键缺口",
            sufficient=False,
            gaps=[],
        )
    with pytest.raises(ValidationError):
        SupervisorDecision(
            action="finish",
            rationale="资料已经充分",
            sufficient=True,
            gaps=["不应存在的关键缺口"],
        )


def test_follow_up_parent_must_reference_an_executed_assignment():
    decision = SupervisorDecision(
        action="dispatch",
        rationale="补充缺口",
        assignments=[
            AssignmentDraft(
                objective="核实日期",
                required_outputs=["确认发布日期"],
                excluded_scope=["不重新梳理全部事件"],
                source_guidance=["官方公告"],
                parent_ids=["r7"],
            )
        ],
    )
    with pytest.raises(ValueError, match="parent"):
        decision.validate_dispatch(executed_ids={"r1"}, max_batch_size=3)


def test_partial_result_requires_specific_gap():
    with pytest.raises(ValidationError):
        ResearcherResult(
            task_id="r1",
            status="partial",
            summary="已有一些资料",
            source_urls=["https://example.com/a"],
            gaps=[],
            stop_reason="round_limit",
        )


def test_assignment_ids_are_stable_program_ids():
    assignment = ResearchAssignment(
        id="r12",
        objective="研究技术",
        required_outputs=["技术变化", "影响"],
        excluded_scope=["融资"],
        source_guidance=["官方公告"],
    )
    assert assignment.id == "r12"


def test_assignment_has_at_most_three_checkable_outputs():
    with pytest.raises(ValidationError):
        AssignmentDraft(
            objective="过宽的研究任务",
            required_outputs=["一", "二", "三", "四"],
        )


def test_researcher_model_tools_require_target_output():
    for tool in RESEARCHER_MODEL_TOOLS:
        required = tool["function"]["parameters"]["required"]
        assert "target_output" in required


def test_usage_total_includes_multi_agent_roles_once():
    usage = UsageBreakdown(
        supervisor=TokenUsage(total_tokens=2),
        researcher=TokenUsage(total_tokens=3),
    )
    assert usage.total.total_tokens == 5
    rendered = format_role_usage(usage)
    assert "Supervisor: 2" in rendered
    assert "Researcher: 3" in rendered
