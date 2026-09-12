from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from deeptrace.domain import (
    BudgetSnapshot,
    CitationRef,
    ConversationIntent,
    ConversationSummary,
    ErrorCategory,
    ErrorRecord,
    Evidence,
    EvidenceLifecycleStatus,
    ExecutionStatus,
    Finding,
    ResearchInput,
    ResearchOutcome,
    ResearchMode,
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
from deeptrace.strategies.workflow.models import QueryPlan, WorkflowEvaluation
from deeptrace.strategies.plan_execute.models import ExecutorDecision, TaskPlan
from deeptrace.responses.models import ResponseDraft


HARNESS_STATE_MSGPACK_TYPES = (
    ConversationSummary,
    Finding,
    ResearchMode,
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
