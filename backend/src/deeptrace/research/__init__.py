"""Contracts and projections for the strategy-independent research runtime."""

from deeptrace.research.adapters import build_contract_and_plan
from deeptrace.research.contract import (
    ContractBudget,
    ResearchAmbiguity,
    ResearchContract,
    SourcePolicy,
)
from deeptrace.research.controller import (
    ControllerDecision,
    ExecutionShape,
    PlanRejectedError,
    decide_execution,
)
from deeptrace.research.critic import (
    PlanIssue,
    PlanIssueSeverity,
    PlanReview,
    review_plan,
)
from deeptrace.research.plan import (
    ExecutionMode,
    PlanTask,
    ResearchPlan,
    TaskBudget,
    TaskType,
)
from deeptrace.research.scheduler import (
    PlanScheduler,
    TaskRunStatus,
)
from deeptrace.research.evidence_graph import (
    Claim,
    ClaimStatus,
    EvidenceGraph,
    EvidenceSource,
    EvidenceSpan,
    build_evidence_graph,
)
from deeptrace.research.verification import (
    VerificationAction,
    VerificationResult,
    project_verification_result,
    verify_evidence_graph,
)

__all__ = [
    "Claim",
    "ClaimStatus",
    "ContractBudget",
    "ControllerDecision",
    "EvidenceGraph",
    "EvidenceSource",
    "EvidenceSpan",
    "ExecutionMode",
    "ExecutionShape",
    "PlanIssue",
    "PlanIssueSeverity",
    "PlanRejectedError",
    "PlanReview",
    "PlanScheduler",
    "PlanTask",
    "ResearchAmbiguity",
    "ResearchContract",
    "ResearchPlan",
    "SourcePolicy",
    "TaskBudget",
    "TaskRunStatus",
    "TaskType",
    "VerificationAction",
    "VerificationResult",
    "build_contract_and_plan",
    "build_evidence_graph",
    "decide_execution",
    "project_verification_result",
    "review_plan",
    "verify_evidence_graph",
]
