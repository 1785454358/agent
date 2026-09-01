"""研究计划与笔记事件时间的确定性关系判断。"""

from datetime import date, datetime

from deeptrace.models import ResearchTimeRange, TemporalRelation


def normalize_temporal_relation(
    time_range: ResearchTimeRange | None,
    source_published_at: datetime | None,
    event_start_date: date | None,
    event_end_date: date | None,
) -> TemporalRelation:
    if time_range is None:
        return "not_applicable"
    if not time_range.start_date or not time_range.end_date or event_start_date is None or event_end_date is None:
        return "unknown"
    if event_start_date > event_end_date:
        raise ValueError("事件起始日期不能晚于结束日期")
    if event_end_date < time_range.start_date or event_start_date > time_range.end_date:
        return "out_of_range"
    if source_published_at and source_published_at.date() > time_range.end_date:
        return "retrospective"
    return "in_range"
