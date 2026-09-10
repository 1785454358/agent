from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from deeptrace.domain import (
    BudgetSnapshot,
    ConversationIntent,
    ConversationSummary,
    ErrorCategory,
    ErrorRecord,
    ExecutionStatus,
    Finding,
    ResearchInput,
    ResearchOutcome,
    ResearchProfile,
    ResponseProfile,
)


HARNESS_STATE_MSGPACK_TYPES = (
    ConversationSummary,
    Finding,
    ResearchProfile,
    ConversationIntent,
    ResponseProfile,
    ExecutionStatus,
    ErrorCategory,
    BudgetSnapshot,
    ErrorRecord,
    ResearchInput,
    ResearchOutcome,
)


def create_harness_checkpoint_serializer() -> JsonPlusSerializer:
    return JsonPlusSerializer(allowed_msgpack_modules=HARNESS_STATE_MSGPACK_TYPES)
