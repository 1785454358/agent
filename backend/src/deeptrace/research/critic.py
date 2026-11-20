"""Host-side plan validation before any task is allowed to execute."""

from __future__ import annotations

from collections.abc import Collection
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from deeptrace.research.contract import ContractText, ResearchContract
from deeptrace.research.plan import PlanTask, ResearchPlan, TaskIdentifier


class PlanIssueSeverity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


class PlanIssue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,63}$")]
    severity: PlanIssueSeverity
    task_ids: tuple[TaskIdentifier, ...] = Field(default_factory=tuple, max_length=12)
    message: ContractText


class PlanReview(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    plan_revision: int = Field(ge=1)
    plan_id: str | None = None
    contract_revision: int | None = Field(default=None, ge=1)
    plan_digest: str | None = None
    accepted: bool
    issues: tuple[PlanIssue, ...] = Field(default_factory=tuple, max_length=100)
    covered_requirement_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=6)
    uncovered_requirement_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=6)
    estimated_model_calls: int = Field(ge=0)
    estimated_pages: int = Field(ge=0)

    @property
    def errors(self) -> tuple[PlanIssue, ...]:
        return tuple(
            issue for issue in self.issues if issue.severity is PlanIssueSeverity.ERROR
        )


def _issue(
    code: str,
    message: str,
    *,
    task_ids: tuple[str, ...] = (),
    severity: PlanIssueSeverity = PlanIssueSeverity.ERROR,
) -> PlanIssue:
    return PlanIssue(
        code=code,
        severity=severity,
        task_ids=task_ids,
        message=message,
    )


def _duplicate_queries(tasks: tuple[PlanTask, ...]) -> tuple[PlanIssue, ...]:
    owners: dict[str, list[str]] = {}
    for task in tasks:
        for query in task.query_seeds:
            normalized = " ".join(query.casefold().split())
            owners.setdefault(normalized, []).append(task.id)
    return tuple(
        _issue(
            "duplicate_query",
            f"query is reused by multiple tasks: {query[:200]}",
            task_ids=tuple(dict.fromkeys(task_ids)),
            severity=PlanIssueSeverity.WARNING,
        )
        for query, task_ids in owners.items()
        if len(set(task_ids)) > 1
    )


def review_plan(
    plan: ResearchPlan,
    contract: ResearchContract,
    *,
    allowed_capabilities: Collection[str] | None = None,
    max_tasks: int = 12,
) -> PlanReview:
    """Return a deterministic verdict; errors block execution, warnings do not."""
    if not 1 <= max_tasks <= 12:
        raise ValueError("max_tasks must be between 1 and 12")

    issues: list[PlanIssue] = []
    if plan.run_id != contract.run_id:
        issues.append(_issue("run_identity_mismatch", "plan and contract use different runs"))
    if plan.contract_revision != contract.revision:
        issues.append(
            _issue(
                "contract_revision_mismatch",
                "plan does not reference the current research contract",
            )
        )
    if contract.requires_clarification:
        issues.append(
            _issue(
                "clarification_required",
                "high risk and high ambiguity must be clarified before planning",
            )
        )
    if len(plan.tasks) > max_tasks:
        issues.append(
            _issue(
                "task_limit_exceeded",
                f"plan has {len(plan.tasks)} tasks; limit is {max_tasks}",
            )
        )

    contract_requirements = [requirement.id for requirement in contract.requirements]
    contract_requirement_set = set(contract_requirements)
    if not contract_requirements:
        issues.append(
            _issue(
                "contract_has_no_requirements",
                "the contract must establish at least one acceptance requirement",
            )
        )
    covered_requirements = {
        requirement_id
        for task in plan.tasks
        for requirement_id in task.requirement_ids
        if requirement_id in contract_requirement_set
    }
    uncovered = [
        requirement_id
        for requirement_id in contract_requirements
        if requirement_id not in covered_requirements
    ]
    for task in plan.tasks:
        unknown = [
            requirement_id
            for requirement_id in task.requirement_ids
            if requirement_id not in contract_requirement_set
        ]
        if unknown:
            issues.append(
                _issue(
                    "unknown_requirement",
                    f"task references requirements outside the contract: {unknown}",
                    task_ids=(task.id,),
                )
            )
    if uncovered:
        issues.append(
            _issue(
                "uncovered_requirements",
                f"no task covers requirements: {uncovered}",
            )
        )

    if allowed_capabilities is not None:
        allowed = set(allowed_capabilities)
        for task in plan.tasks:
            unknown = [name for name in task.capabilities if name not in allowed]
            if unknown:
                issues.append(
                    _issue(
                        "unknown_capability",
                        f"task requests unavailable capabilities: {unknown}",
                        task_ids=(task.id,),
                    )
                )

    available_calls = (
        contract.budget.max_model_calls - contract.budget.finishing_calls
    )
    estimated_model_calls = sum(task.budget.max_calls for task in plan.tasks)
    estimated_pages = sum(task.budget.max_pages for task in plan.tasks)
    if estimated_model_calls > available_calls:
        issues.append(
            _issue(
                "budget_infeasible",
                "task budgets exceed the model calls reserved for research",
            )
        )

    issues.extend(_duplicate_queries(plan.tasks))
    return PlanReview(
        plan_revision=plan.revision,
        plan_id=plan.plan_id,
        contract_revision=plan.contract_revision,
        plan_digest=plan.content_digest,
        accepted=not any(
            issue.severity is PlanIssueSeverity.ERROR for issue in issues
        ),
        issues=tuple(issues),
        covered_requirement_ids=tuple(
            requirement_id
            for requirement_id in contract_requirements
            if requirement_id in covered_requirements
        ),
        uncovered_requirement_ids=tuple(uncovered),
        estimated_model_calls=estimated_model_calls,
        estimated_pages=estimated_pages,
    )
