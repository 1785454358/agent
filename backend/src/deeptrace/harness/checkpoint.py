from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.types import Overwrite
from deeptrace.domain.delivery import DeliveryPlan, EvidenceNeed

from deeptrace.domain import (
    BudgetSnapshot,
    CitationRef,
    ConversationIntent,
    ConversationSummary,
    CoverageAssessment,
    ErrorCategory,
    ErrorRecord,
    Evidence,
    EvidenceLifecycleStatus,
    EvidenceSupport,
    ExecutionStatus,
    Finding,
    RequirementCoverage,
    ResearchInput,
    ResearchMode,
    ResearchOutcome,
    ResearchRequirement,
    ResearchTopicInput,
    ResearchTopicOutcome,
    ResponseInput,
    ResponseMode,
    ResponseOutcome,
    ToolName,
    ToolRequest,
    ToolResult,
    TopicStepError,
)
from deeptrace.domain.agent import AgentOutcome
from deeptrace.domain.tools import CustomToolName
from deeptrace.domain.evidence_anchor import ReadEvidenceAnchor
from deeptrace.harness.agent_state import AgentTodo, TodoStatus
from deeptrace.research import (
    Claim,
    ClaimStatus,
    ContractBudget,
    ControllerDecision,
    EvidenceGraph,
    EvidenceSource,
    EvidenceSpan,
    ExecutionMode,
    ExecutionShape,
    PlanIssue,
    PlanIssueSeverity,
    PlanReview,
    PlanTask,
    ResearchAmbiguity,
    ResearchContract,
    ResearchPlan,
    SourcePolicy,
    TaskBudget,
    TaskRunStatus,
    TaskType,
    VerificationAction,
    VerificationResult,
)
from deeptrace.responses.models import ResponseDraft
from deeptrace.strategies.evidence_evaluation import FindingDraft, SupportDraft
from deeptrace.strategies.evidence_references import (
    ReferenceFindingDraft,
    ReferenceSupportDraft,
)
from deeptrace.strategies.multi_agent.models import (
    ReferenceSupervisorEvaluation,
    SupervisorEvaluation,
)
from deeptrace.strategies.plan_execute.models import (
    ExecutorDecision,
    ReferenceExecutorDecision,
    TaskPlan,
)
from deeptrace.strategies.workflow.models import (
    QueryPlan,
    ReferenceWorkflowEvaluation,
    WorkflowEvaluation,
)

HARNESS_STATE_MSGPACK_TYPES = (
    DeliveryPlan,
    EvidenceNeed,
    Overwrite,
    CustomToolName,
    ReferenceSupportDraft,
    ReferenceFindingDraft,
    ReferenceSupervisorEvaluation,
    ReferenceExecutorDecision,
    ReferenceWorkflowEvaluation,
    ReadEvidenceAnchor,
    AgentOutcome,
    AgentTodo,
    TodoStatus,
    ConversationSummary,
    Finding,
    FindingDraft,
    SupportDraft,
    ResearchMode,
    EvidenceSupport,
    CoverageAssessment,
    ResearchRequirement,
    RequirementCoverage,
    ConversationIntent,
    ResponseMode,
    ExecutionStatus,
    ErrorCategory,
    BudgetSnapshot,
    ErrorRecord,
    ResearchInput,
    ResearchOutcome,
    ResearchTopicInput,
    ResearchTopicOutcome,
    TopicStepError,
    QueryPlan,
    WorkflowEvaluation,
    TaskPlan,
    ExecutorDecision,
    SupervisorEvaluation,
    CitationRef,
    ResponseDraft,
    ResponseInput,
    ResponseOutcome,
    ToolName,
    ToolRequest,
    ToolResult,
    Evidence,
    EvidenceLifecycleStatus,
    Claim,
    ClaimStatus,
    ContractBudget,
    ControllerDecision,
    EvidenceGraph,
    EvidenceSource,
    EvidenceSpan,
    ExecutionMode,
    ExecutionShape,
    PlanIssue,
    PlanIssueSeverity,
    PlanReview,
    PlanTask,
    ResearchAmbiguity,
    ResearchContract,
    ResearchPlan,
    SourcePolicy,
    TaskBudget,
    TaskRunStatus,
    TaskType,
    VerificationAction,
    VerificationResult,
)


def subgraph_config(config):
    """Forward checkpoint coordinates without requesting replay at a null ID.

    Parent task configs include checkpoint_id=None. The installed runtime treats
    presence of that key as explicit replay, which reruns successful pending
    writes. Real checkpoint IDs (intentional time travel) remain unchanged.
    """
    if config is None:
        return None
    configurable = dict(config.get("configurable") or {})
    if configurable.get("checkpoint_id") is None:
        configurable.pop("checkpoint_id", None)
    return {**config, "configurable": configurable}


def create_harness_checkpoint_serializer() -> JsonPlusSerializer:
    return JsonPlusSerializer(allowed_msgpack_modules=HARNESS_STATE_MSGPACK_TYPES)
