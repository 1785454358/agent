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
    ResponseInput,
    ResponseMode,
    ResponseOutcome,
    ToolName,
    ToolRequest,
    ToolResult,
)


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
    CitationRef,
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
