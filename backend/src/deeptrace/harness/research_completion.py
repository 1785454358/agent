"""Host-checked branch completion; global evidence coverage remains separate."""

from pydantic import BaseModel, ConfigDict, Field, field_validator

from deeptrace.domain.evidence import EvidenceLifecycleStatus
from deeptrace.domain.evidence_anchor import ReadEvidenceAnchor
from deeptrace.harness.agent_state import TodoStatus


class FinishResearchArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")
    summary: str = Field(min_length=1, max_length=1000)

    @field_validator("summary")
    @classmethod
    def nonblank_summary(cls, value):
        if not value.strip():
            raise ValueError("empty_finish_summary")
        return value.strip()


async def validate_completion(*, task, findings, todos, context, read_anchors=()):
    if any(t.status != TodoStatus.COMPLETED for t in todos):
        raise ValueError("finish_open_todos")
    sources = {}
    for raw_anchor in read_anchors:
        try:
            anchor = ReadEvidenceAnchor.model_validate(
                raw_anchor.model_dump()
                if isinstance(raw_anchor, ReadEvidenceAnchor)
                else raw_anchor
            )
        except ValueError:
            continue
        if anchor.evidence_id not in task.authorized_evidence_ids:
            continue
        if anchor.evidence_id not in sources:
            try:
                sources[anchor.evidence_id] = (
                    await context.evidence_store.get(
                        context.workspace_id, anchor.evidence_id
                    ),
                    await context.evidence_store.read_body(
                        context.workspace_id, anchor.evidence_id
                    ),
                )
            except KeyError:
                continue
        record, body = sources[anchor.evidence_id]
        if (
            record.status is EvidenceLifecycleStatus.ACTIVE
            and anchor.version == record.version
            and anchor.content_hash == record.content_hash
            and 0 <= anchor.start < anchor.end <= len(body)
        ):
            return
    raise ValueError("finish_no_valid_reads")
