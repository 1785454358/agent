from deeptrace.models import RunEvent


def test_run_event_details_are_not_shared() -> None:
    first = RunEvent(event_type="planning.started", message="开始")
    second = RunEvent(event_type="planning.started", message="开始")

    first.details["count"] = 1

    assert second.details == {}
