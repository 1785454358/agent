from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from deeptrace.domain import (
    BudgetSnapshot,
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
    ResponseMode,
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
    ToolName,
    ToolRequest,
    ToolResult,
    Evidence,
    EvidenceLifecycleStatus,
)


def create_harness_checkpoint_serializer() -> JsonPlusSerializer:
    return JsonPlusSerializer(allowed_msgpack_modules=HARNESS_STATE_MSGPACK_TYPES)
