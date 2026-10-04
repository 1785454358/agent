"""Bounded coverage contracts independent of graph/execution dependencies."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ResearchRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^r[1-6]$")
    description: str = Field(min_length=1, max_length=500)


class RequirementCoverage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirement_id: str = Field(pattern=r"^r[1-6]$")
    status: Literal["covered", "missing", "conflicting"]
    reason: str = Field(min_length=1, max_length=500)
    finding_ids: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("finding_ids")
    @classmethod
    def unique_findings(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("finding_ids must be unique")
        return value


class CoverageAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[RequirementCoverage] = Field(min_length=1, max_length=6)

    @field_validator("items")
    @classmethod
    def unique_requirements(
        cls, value: list[RequirementCoverage]
    ) -> list[RequirementCoverage]:
        ids = [item.requirement_id for item in value]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate_requirement_coverage")
        return value
