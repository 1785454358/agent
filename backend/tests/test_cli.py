from types import SimpleNamespace

from deeptrace.cli import (
    _exit_code,
    _format_stage_four_summary,
    _parser,
    _print_event,
)
from deeptrace.models import RunEvent


def test_parser_describes_planned_research() -> None:
    parser = _parser()
    args = parser.parse_args(["研究问题"])

    assert args.question == "研究问题"
    assert "规划式" in parser.description


def test_event_formatter_prints_message_only(capsys) -> None:
    _print_event(RunEvent(event_type="planning.started", message="开始规划"))

    assert capsys.readouterr().out == "开始规划\n"


def test_exit_status_maps_partial_results_to_nonzero() -> None:
    assert _exit_code("completed") == 0
    assert _exit_code("partial") == 2


def test_stage_four_cli_summary_reports_evidence_and_verdicts() -> None:
    result = SimpleNamespace(
        evidence_location_counts={"exact": 4, "unlocated": 1},
        verdict_counts={"verified": 2, "unsupported": 1},
        verification_gap_count=1,
        supplement_rounds=1,
        used_claim_ids=["claim-01", "claim-02"],
        sources=["https://example.com/a"],
    )

    rendered = _format_stage_four_summary(result)

    assert "exact=4" in rendered
    assert "verified=2" in rendered
    assert "Gap=1" in rendered
    assert "使用 Claim=2" in rendered
