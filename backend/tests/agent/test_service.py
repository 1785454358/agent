from decimal import Decimal

from deeptrace.agent.service import _initial_stage_four_state, _sources_from_used_notes
from deeptrace.agent.writer import sources_from_used_claims
from deeptrace.models import TokenUsage
from deeptrace.observability import estimate_usage_cost


def test_sources_follow_writer_note_order(research_note) -> None:
    second = research_note.model_copy(
        update={"note_id": "note-02", "source_url": "https://example.com/b"}
    )

    sources = _sources_from_used_notes(
        {research_note.note_id: research_note, second.note_id: second},
        [second.note_id, research_note.note_id, second.note_id],
    )

    assert sources == ["https://example.com/b", "https://example.com/a"]


def test_usage_cost_uses_decimal_prices() -> None:
    cost = estimate_usage_cost(
        TokenUsage(input_tokens=1_000_000, output_tokens=500_000),
        Decimal("2.00"),
        Decimal("4.00"),
    )

    assert cost == Decimal("4.00")


def test_stage_four_state_is_fully_initialized() -> None:
    state = _initial_stage_four_state("研究问题")

    assert state["sources"] == {}
    assert state["evidence"] == {}
    assert state["claims"] == {}
    assert state["verification_results"] == {}
    assert state["verification_gaps"] == {}
    assert state["task_verification"] == {}
    assert state["verification_task_id"] is None
    assert state["verification_mode"] == "done"
    assert state["verification_tool_rounds"] == 0
    assert state["used_claim_ids"] == []
