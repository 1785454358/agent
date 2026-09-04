from deeptrace.cli import _exit_code, _parser, _print_event
from deeptrace.models import RunEvent


def test_parser_describes_basic_parallel_research() -> None:
    parser = _parser()
    args = parser.parse_args(["研究问题"])

    assert args.question == "研究问题"
    assert "并行" in parser.description


def test_event_formatter_prints_message_only(capsys) -> None:
    _print_event(RunEvent(event_type="planning.started", message="开始规划"))

    assert capsys.readouterr().out == "开始规划\n"


def test_exit_status_maps_partial_results_to_nonzero() -> None:
    assert _exit_code("completed") == 0
    assert _exit_code("partial") == 2
