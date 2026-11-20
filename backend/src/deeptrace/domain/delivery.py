"""A provisional solution to investigate, never evidence or user authority."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

PlanText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=600)]


class EvidenceNeed(BaseModel):
    model_config = ConfigDict(extra="forbid")
    requirement_id: str = Field(pattern=r"^r[1-6]$")
    query: str = Field(min_length=1, max_length=300)


class DeliveryPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    approach: PlanText
    assumptions: list[PlanText] = Field(default_factory=list, max_length=4)
    outline: list[PlanText] = Field(min_length=1, max_length=6)
    evidence_needs: list[EvidenceNeed] = Field(min_length=1, max_length=6)
    consistency_checks: list[PlanText] = Field(min_length=1, max_length=6)

    @model_validator(mode="after")
    def unique_needs_and_checks(self):
        ids = [need.requirement_id for need in self.evidence_needs]
        queries = [" ".join(need.query.casefold().split()) for need in self.evidence_needs]
        if len(set(ids)) != len(ids) or not all(queries) or len(set(queries)) != len(queries):
            raise ValueError("ambiguous_evidence_needs")
        if len(set(self.consistency_checks)) != len(self.consistency_checks):
            raise ValueError("duplicate_consistency_checks")
        return self
