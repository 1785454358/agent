from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

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
from deeptrace.domain.evidence_anchor import ReadEvidenceAnchor
from deeptrace.harness.agent_state import AgentTodo, TodoStatus
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
)


def create_harness_checkpoint_serializer() -> JsonPlusSerializer:
    return JsonPlusSerializer(allowed_msgpack_modules=HARNESS_STATE_MSGPACK_TYPES)
