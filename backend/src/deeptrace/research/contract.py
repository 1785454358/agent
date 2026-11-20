"""The host-owned research contract, independent of orchestration strategy."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from deeptrace.domain.coverage import ResearchRequirement
from deeptrace.domain.execution import ExecutionIdentifier, ResearchInput
from deeptrace.domain.research import SourceDomain

ContractText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)
]
GoalText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20_000)
]
RiskLevel = Literal["low", "medium", "high"]
AmbiguityLevel = Literal["low", "high"]


class ContractBudget(BaseModel):
    """Call, input, wall-clock and optional cost limits for one research run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    max_model_calls: int = Field(default=20, ge=1, le=100)
    max_input_tokens: int = Field(default=100_000, ge=1, le=10_000_000)
    max_seconds: float = Field(default=600.0, gt=0, le=86_400)
    max_cost_usd: Decimal | None = Field(default=None, ge=0)
    finishing_calls: int = Field(default=3, ge=1, le=10)

    @model_validator(mode="after")
    def reserve_finishing_calls(self) -> ContractBudget:
        if self.finishing_calls >= self.max_model_calls:
            raise ValueError("finishing_calls must leave research call capacity")
        return self


class SourcePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: Literal["general", "research_results", "corpus"] = "general"
    domains: tuple[SourceDomain, ...] = Field(default_factory=tuple, max_length=4)
    publication_years: tuple[
        Annotated[int, Field(strict=True, ge=1900, le=2100)], ...
    ] = Field(default_factory=tuple, max_length=3)

    @field_validator("domains", "publication_years")
    @classmethod
    def unique_values(cls, value: tuple, info) -> tuple:
        if len(value) != len(set(value)):
            raise ValueError(f"{info.field_name} must be unique")
        return value


class ResearchAmbiguity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    level: AmbiguityLevel = "low"
    questions: tuple[ContractText, ...] = Field(default_factory=tuple, max_length=4)

    @model_validator(mode="after")
    def questions_match_level(self) -> ResearchAmbiguity:
        if self.level == "high" and not self.questions:
            raise ValueError("high ambiguity requires clarification questions")
        if self.level == "low" and self.questions:
            raise ValueError("low ambiguity cannot carry clarification questions")
        return self


class ResearchContract(BaseModel):
    """The authoritative target; a planner may propose it but never amend it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: ExecutionIdentifier
    goal: GoalText
    user_constraints: tuple[ContractText, ...] = Field(default_factory=tuple, max_length=50)
    assumptions: tuple[ContractText, ...] = Field(default_factory=tuple, max_length=4)
    requirements: tuple[ResearchRequirement, ...] = Field(default_factory=tuple, max_length=6)
    source_policy: SourcePolicy = SourcePolicy()
    risk: RiskLevel = "low"
    budget: ContractBudget = ContractBudget()
    ambiguity: ResearchAmbiguity = ResearchAmbiguity()
    revision: int = Field(default=1, ge=1)
    parent_revision: int | None = Field(default=None, ge=1)
    revision_reason: ContractText | None = None

    @model_validator(mode="after")
    def valid_contract(self) -> ResearchContract:
        requirement_ids = [requirement.id for requirement in self.requirements]
        if len(requirement_ids) != len(set(requirement_ids)):
            raise ValueError("requirement ids must be unique")
        if self.revision == 1 and self.parent_revision is not None:
            raise ValueError("the initial contract cannot have a parent revision")
        if self.revision > 1 and (
            self.parent_revision is None
            or self.parent_revision >= self.revision
            or self.revision_reason is None
        ):
            raise ValueError("a contract revision requires its parent and reason")
        if self.revision > 1 and not self.requirements:
            raise ValueError("a contract revision cannot discard acceptance criteria")
        return self

    @property
    def requires_clarification(self) -> bool:
        return self.risk == "high" and self.ambiguity.level == "high"

    def with_requirements(
        self, requirements: tuple[ResearchRequirement, ...], *, reason: ContractText
    ) -> ResearchContract:
        """Return a new revision; the previous authoritative target is unchanged."""
        return type(self).model_validate(
            {
                **self.model_dump(exclude={"requirements", "revision", "parent_revision", "revision_reason"}),
                "requirements": requirements,
                "revision": self.revision + 1,
                "parent_revision": self.revision,
                "revision_reason": reason,
            }
        )

    @classmethod
    def from_research_input(
        cls, research_input: ResearchInput, *, budget: ContractBudget | None = None
    ) -> ResearchContract:
        """Project the legacy session input without inventing evidence requirements."""
        return cls(
            run_id=research_input.run_id,
            goal=research_input.question,
            user_constraints=tuple(research_input.conversation_summary.user_constraints),
            budget=budget or ContractBudget(),
        )
