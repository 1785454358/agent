from deeptrace.cli import _exit_code, _parser, _print_event


def test_cli_can_select_plan_execute_research():
    assert (
        _parser().parse_args(["--mode", "plan_execute", "研究问题"]).mode
        == "plan_execute"
    )


def test_cli_can_select_multi_agent_research():
    assert (
        _parser().parse_args(["--mode", "multi_agent", "研究问题"]).mode
        == "multi_agent"
    )


from deeptrace.models import RunEvent


def test_parser_defaults_to_workflow_and_normalizes_legacy_names() -> None:
    parser = _parser()
    args = parser.parse_args(["研究问题"])

    assert args.question == "研究问题"
    assert args.mode == "workflow"


def test_event_formatter_prints_message_only(capsys) -> None:
    _print_event(RunEvent(event_type="planning.started", message="开始规划"))

    assert capsys.readouterr().out == "开始规划\n"


def test_exit_status_maps_partial_results_to_nonzero() -> None:
    assert _exit_code("completed") == 0
    assert _exit_code("partial") == 2
