from pydantic import BaseModel, Field, field_validator


class Finding(BaseModel):
    id: str = Field(min_length=1)
    claim: str = Field(min_length=1)
    evidence_ids: list[str] = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("evidence_ids")
    @classmethod
    def unique_evidence_ids(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("evidence_ids must be unique")
        return value
