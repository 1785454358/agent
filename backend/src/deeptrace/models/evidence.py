"""阶段 4 的证据与主张数据模型。"""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from deeptrace.models.document import ScraperUsed
from deeptrace.models.quality import SourceKind, TemporalRelation


SourceChannel = Literal["web"]
EvidenceLocationStatus = Literal["exact", "unlocated"]
ClaimKind = Literal["factual", "numeric", "comparative", "temporal"]
ClaimImportance = Literal["key", "supporting"]


class Source(BaseModel):
    """一次抓取后归一化的来源元数据。"""

    source_id: str = Field(min_length=1)
    doc_id: str = Field(min_length=1)
    requested_url: str = Field(min_length=1)
    final_url: str = Field(min_length=1)
    canonical_url: str | None = Field(default=None, min_length=1)
    title: str = Field(min_length=1)
    publisher: str | None = None
    source_kind: SourceKind
    channel: SourceChannel = "web"
    publication_date: datetime | None = None
    modified_date: datetime | None = None
    fetched_at: datetime
    scraper_used: ScraperUsed
    content_hash: str = Field(min_length=1)


class Evidence(BaseModel):
    """可回溯到文档原文的证据片段。"""

    evidence_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    doc_id: str = Field(min_length=1)
    note_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    section_id: str = Field(min_length=1)
    quote: str = Field(min_length=1)
    quote_hash: str = Field(min_length=1)
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, ge=0)
    location_status: EvidenceLocationStatus
    event_start: date | None = None
    event_end: date | None = None
    temporal_relation: TemporalRelation = "unknown"

    @model_validator(mode="after")
    def validate_exact_location(self) -> "Evidence":
        """精确定位必须同时给出合法的字符区间。"""
        if self.location_status == "exact":
            if self.char_start is None or self.char_end is None:
                raise ValueError("精确证据必须包含字符位置")
            if self.char_end <= self.char_start:
                raise ValueError("证据字符位置的结束值必须大于开始值")
        return self


class NumericDetail(BaseModel):
    """数值主张的结构化细节。"""

    value_text: str = Field(min_length=1)
    unit: str | None = None
    scope: str | None = None
    time_basis: str | None = None


class Claim(BaseModel):
    """从草稿中抽取、等待核验的原子主张。"""

    claim_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    section_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    kind: ClaimKind
    importance: ClaimImportance
    event_start: date | None = None
    event_end: date | None = None
    numeric: NumericDetail | None = None
    evidence_ids: list[str] = Field(default_factory=list)
