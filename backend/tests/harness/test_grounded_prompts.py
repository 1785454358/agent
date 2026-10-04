from deeptrace.harness.prompts import RESEARCH_SYSTEM_INSTRUCTION
from deeptrace.strategies.planning import planning_instruction


def test_shared_prompts_explain_actionable_fact_completion():
    assert "record_findings" in RESEARCH_SYSTEM_INSTRUCTION
    assert "find" in RESEARCH_SYSTEM_INSTRUCTION
    for field in ("queries", "assignments"):
        assert "条件" in planning_instruction(field, 3)
        assert "明确" in planning_instruction(field, 3)
