"""Bounded coverage contracts independent of graph/execution dependencies."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator


class ResearchRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=r"^r[1-6]$")
    description: str = Field(min_length=1, max_length=500)
    required: bool = Field(default=True, strict=True)
    allow_unknown: bool = Field(default=False, strict=True)
    user_quote: str | None = Field(default=None,min_length=1,max_length=500)


class RequirementCoverage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirement_id: str = Field(pattern=r"^r[1-6]$")
    status: Literal["covered", "missing", "conflicting"]
    reason: str = Field(min_length=1, max_length=500)
    finding_ids: list[str] = Field(default_factory=list, max_length=50)
    unanswered_parts: list[Annotated[str, StringConstraints(
        strip_whitespace=True, min_length=1, max_length=300
    )]] = Field(default_factory=list, max_length=6)
    resolution: Literal["answered", "unread", "not_found", "not_disclosed", "incomparable"] | None = None
    limitations: list[Annotated[str, Field(min_length=1,max_length=300)]] = Field(default_factory=list,max_length=6)

    @model_validator(mode="after")
    def incomplete_parts_block_coverage(self):
        if self.unanswered_parts and self.status == "covered":
            self.status = "missing"
        return self

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


def requirements_satisfied(requirements, coverage) -> bool:
    required={r.id for r in requirements if r.required}
    items={item.requirement_id:item for item in coverage.items} if coverage else {}
    return bool(required) and all(identity in items and items[identity].status=="covered" for identity in required)
