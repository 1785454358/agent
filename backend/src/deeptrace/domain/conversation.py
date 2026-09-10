from typing import Annotated

from pydantic import BaseModel, Field


MAX_TOPIC_LENGTH = 500
MAX_SUMMARY_ITEM_LENGTH = 500
MAX_REFERENCED_ENTITIES = 100
MAX_ENTITY_KEY_LENGTH = 100
MAX_ENTITY_VALUE_LENGTH = 500

SummaryItem = Annotated[str, Field(max_length=MAX_SUMMARY_ITEM_LENGTH)]
EntityKey = Annotated[str, Field(max_length=MAX_ENTITY_KEY_LENGTH)]
EntityValue = Annotated[str, Field(max_length=MAX_ENTITY_VALUE_LENGTH)]


class ConversationSummary(BaseModel):
    topic: str = Field(default="", max_length=MAX_TOPIC_LENGTH)
    user_constraints: list[SummaryItem] = Field(default_factory=list, max_length=50)
    established_facts: list[SummaryItem] = Field(default_factory=list, max_length=100)
    referenced_entities: dict[EntityKey, EntityValue] = Field(
        default_factory=dict,
        max_length=MAX_REFERENCED_ENTITIES,
    )
    unresolved_questions: list[SummaryItem] = Field(default_factory=list, max_length=50)
    previous_conclusions: list[SummaryItem] = Field(default_factory=list, max_length=50)
