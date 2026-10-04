"""Authorized read-only access to stored evidence, with complete bounded JSON."""

import json
from dataclasses import asdict

from pydantic import BaseModel, ConfigDict, Field, model_validator

from deeptrace.domain.evidence import (
    Evidence,
    EvidenceIdentifier,
    EvidenceLifecycleStatus,
)
from deeptrace.domain.tools import MAX_TOOL_PREVIEW_LENGTH
from deeptrace.tools.contracts import ToolAdapterResult, ToolCallContext
from deeptrace.tools.evidence_store import EvidenceStore
from deeptrace.tools.evidence_views import (
    EvidencePassage,
    make_evidence_passage,
    select_evidence_passages,
    select_source_excerpt,
)


class ReadEvidenceArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: EvidenceIdentifier
    query: str | None = Field(default=None, min_length=1, max_length=1000)
    start: int | None = Field(default=None, ge=0, strict=True)
    find: str | None = Field(default=None, min_length=1, max_length=200)
    after: int | None = Field(default=None, ge=0, strict=True)
    limit: int = Field(default=2000, ge=1, le=3000, strict=True)

    @model_validator(mode="after")
    def exclusive_selector(self) -> "ReadEvidenceArguments":
        if sum(value is not None for value in (self.query, self.start, self.find)) > 1:
            raise ValueError("read_selectors_are_exclusive")
        if self.after is not None and self.find is None:
            raise ValueError("after_requires_find")
        if self.find is not None and len(self.find) > self.limit:
            raise ValueError("find_exceeds_limit")
        return self


class ReadEvidenceAdapter:
    def __init__(self, store: EvidenceStore) -> None:
        self._store = store

    async def _record(self, arguments: BaseModel, context: ToolCallContext) -> Evidence:
        if not isinstance(arguments, ReadEvidenceArguments):
            raise TypeError("read arguments have the wrong type")
        grant = context.evidence_authorization
        if grant is None or arguments.evidence_id not in grant.evidence_ids:
            raise PermissionError("evidence_not_authorized")
        record = await self._store.get(context.tenant_id, arguments.evidence_id)
        if record.status is EvidenceLifecycleStatus.DELETED:
            raise KeyError("evidence_unavailable")
        if record.status is EvidenceLifecycleStatus.ACTIVE:
            return record
        historical_statuses = {
            EvidenceLifecycleStatus.STALE,
            EvidenceLifecycleStatus.SUPERSEDED,
            EvidenceLifecycleStatus.EXPIRED,
        }
        if record.status in historical_statuses and record.id in grant.historical_ids:
            return record
        raise PermissionError("evidence_not_authorized")

    async def preflight(self, arguments: BaseModel, context: ToolCallContext) -> None:
        await self._record(arguments, context)

    async def read(
        self, arguments: BaseModel, context: ToolCallContext
    ) -> ToolAdapterResult:
        try:
            record = await self._record(arguments, context)
            body = await self._store.read_body(context.tenant_id, record.id)
        except PermissionError:
            return ToolAdapterResult.failure("evidence_not_authorized")
        except KeyError:
            return ToolAdapterResult.failure("evidence_unavailable")
        assert isinstance(arguments, ReadEvidenceArguments)
        selection = {}
        strategy = (
            "find"
            if arguments.find is not None
            else "range"
            if arguments.start is not None
            else "query"
            if arguments.query
            else "prefix"
        )
        if arguments.find is not None:
            position = body.find(arguments.find, arguments.after or 0)
            selection = {"found": position >= 0, "next_start": None}
            if position < 0:
                selection.update(
                    reason="find_no_match",
                    hint="按本分支问题使用query选段；find仅定位已见原文，不猜测整句。",
                )
            passages = ()
            if position >= 0:
                selection["next_start"] = position + len(arguments.find)
                before = min(120, (arguments.limit - len(arguments.find)) // 2)
                start = max(0, position - before)
                passages = (
                    make_evidence_passage(
                        record, body, start, min(len(body), start + arguments.limit)
                    ),
                )
        elif arguments.query is not None:
            excerpt = select_source_excerpt(body, arguments.query, arguments.limit)
            passages = tuple(
                make_evidence_passage(record, body, r.start, r.end)
                for r in excerpt.ranges
            )
            selection = {
                "found": None if excerpt.strategy == "full" else bool(passages)
            }
            if excerpt.strategy == "full":
                strategy = "full"
            if excerpt.strategy in {"no_match", "budget_omitted"}:
                selection.update(
                    reason="query_" + excerpt.strategy,
                    hint="缩短为问题中的目标术语；已有定位时可显式读取原文范围。",
                )
        else:
            passages = select_evidence_passages(
                record,
                body,
                query=arguments.query,
                start=arguments.start,
                limit=arguments.limit,
            )
        preview = _fit_preview(
            record,
            body,
            passages,
            strategy=strategy,
            selection=selection,
        )
        if (
            arguments.find is not None
            and selection["found"]
            and not any(
                arguments.find in p["text"] for p in json.loads(preview)["passages"]
            )
        ):
            return ToolAdapterResult.failure("evidence_match_context_limit")
        return ToolAdapterResult(
            preview=preview, data_ref=f"evidence://{record.id}/body"
        )


def _fit_preview(
    record: Evidence,
    body: str,
    passages: tuple[EvidencePassage, ...],
    *,
    strategy: str,
    selection: dict | None = None,
) -> str:
    selection = dict(selection or {})

    def render(selected):
        return json.dumps(
            {
                "evidence_id": record.id,
                "version": record.version,
                "content_hash": record.content_hash,
                "historical": record.status is not EvidenceLifecycleStatus.ACTIVE,
                "passages": [asdict(p) for p in selected],
                "selection": {
                    "strategy": strategy,
                    "body_length": len(body),
                    "omitted": sum(len(p.text) for p in selected) != len(body),
                    **selection,
                },
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )

    selected = list(passages)
    while len(render(selected)) > MAX_TOOL_PREVIEW_LENGTH:
        if not selected:
            raise ValueError("evidence_preview_metadata_too_large")
        last = selected.pop()
        if strategy in {"query", "full"}:
            selection["reason"] = "preview_budget_omitted"
            selection["found"] = bool(selected)
            continue
        # Fit escaped JSON, not just raw text. Rebuild both coordinates and ID.
        low, high = last.start, last.end
        best = None
        while low < high:
            end = (low + high + 1) // 2
            candidate = make_evidence_passage(record, body, last.start, end)
            if len(render([*selected, candidate])) <= MAX_TOOL_PREVIEW_LENGTH:
                best, low = candidate, end
            else:
                high = end - 1
        if best is not None:
            selected.append(best)
            break
    return render(selected)
