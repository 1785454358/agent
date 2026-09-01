"""阶段 3 研究时间与来源质量元数据。"""

from typing import Literal

SourceKind = Literal["official", "academic", "reputable_secondary", "other", "unknown"]
TemporalRelation = Literal["in_range", "retrospective", "out_of_range", "unknown", "not_applicable"]
