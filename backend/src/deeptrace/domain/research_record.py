"""Small research products whose field values address Finding.supports."""

from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


class StudyIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["original_theory", "original_experiment", "method", "review", "background", "unknown"]
    title: str = Field(min_length=1, max_length=300)
    published_on: date


class ObservedValue(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
    support_indices: list[Annotated[int, Field(strict=True, ge=0, lt=128)]] = Field(min_length=1, max_length=12)


class ExperimentRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model: ObservedValue | None = None
    dataset: ObservedValue | None = None
    budget: ObservedValue | None = None
    metric: ObservedValue | None = None
    result: ObservedValue | None = None
    conditions: ObservedValue | None = None
