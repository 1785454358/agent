from datetime import UTC, date, datetime

from deeptrace.context import normalize_temporal_relation
from deeptrace.models import ResearchTimeRange


RANGE_2024 = ResearchTimeRange(
    start_date=date(2024, 1, 1),
    end_date=date(2024, 12, 31),
    description="2024",
)


def test_later_review_of_2024_is_retrospective() -> None:
    assert normalize_temporal_relation(
        RANGE_2024,
        datetime(2026, 2, 1, tzinfo=UTC),
        date(2024, 3, 1),
        date(2024, 3, 1),
    ) == "retrospective"


def test_later_event_is_out_of_range() -> None:
    assert normalize_temporal_relation(
        RANGE_2024,
        datetime(2026, 2, 1, tzinfo=UTC),
        date(2026, 1, 1),
        date(2026, 1, 1),
    ) == "out_of_range"


def test_untimed_question_is_not_applicable() -> None:
    assert normalize_temporal_relation(None, None, None, None) == "not_applicable"
