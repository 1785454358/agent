"""Offline corpus adapters and the eval-shaped runtime context.

Only the search/fetch adapters differ from production. Every governed boundary
(``AgentToolGateway``, budgets, cache, execution ledger, Evidence store) is the
real implementation, so Tier 1 exercises the same runtime path as Tier 0/2.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime

from deeptrace.domain import ResearchMode
from deeptrace.eval.dataset import CorpusDocument
from deeptrace.eval.telemetry import ModelTelemetry, RequestCounter
from deeptrace.eval.trajectory import TrajectoryRecorder
from deeptrace.harness.context import HarnessContext
from deeptrace.harness.memory.store import InMemoryMemoryStore
from deeptrace.models import RawDocument, ScraperUsed
from deeptrace.tools import AgentToolGateway, build_research_tool_registry
from deeptrace.tools.budget import BudgetScopeKey, BudgetUnits, InMemoryBudgetManager
from deeptrace.tools.cache import InMemorySuccessCache, SuccessCacheSingleflight
from deeptrace.tools.evidence_store import InMemoryEvidenceStore
from deeptrace.tools.execution_store import InMemoryToolExecutionStore
from deeptrace.tools.policy import (
    DeterministicUrlSecurityPolicy,
    StaticToolAllowlist,
)
from deeptrace.tools.scraper import WebFetchError
from deeptrace.tools.scraper.urls import normalize_url_before_fetch

DEFAULT_BUDGET = BudgetUnits(tool_calls=60, network_requests=90, fetched_pages=60)
FIXED_NOW = datetime(2026, 9, 12, 8, 0, 0, tzinfo=UTC)


def _tokens(value: str) -> set[str]:
    return {token.casefold() for token in re.findall(r"\w+", value)}


@dataclass(frozen=True)
class EvalFaults:
    """Deterministic failures used to probe recovery and partial-success paths.

    ``fetch`` maps a page URL to a fault mode:

    - ``"empty"``: return a failed/empty document (agent-recoverable);
    - ``"transient_once"``: first attempt raises a retryable timeout, then succeeds;
    - ``"transient_always"``: every attempt raises a retryable timeout;
    - ``"raise"``: raise an unhandled error (maps to a fatal tool failure).

    ``search_queries`` forces ``search_failed`` for the listed queries.
    """

    fetch: Mapping[str, str] = field(default_factory=dict)
    search_queries: frozenset[str] = frozenset()


class Corpus:
    """In-memory document set with deterministic keyword retrieval."""

    def __init__(self, documents: list[CorpusDocument]) -> None:
        if not documents:
            raise ValueError("corpus must contain at least one document")
        self._documents = tuple(documents)
        self._by_url: dict[str, CorpusDocument] = {}
        for document in documents:
            normalized = normalize_url_before_fetch(document.url)
            if normalized in self._by_url:
                raise ValueError(f"duplicate corpus url: {normalized}")
            self._by_url[normalized] = document

    def documents(self) -> tuple[CorpusDocument, ...]:
        return self._documents

    def document_for(self, url: str) -> CorpusDocument | None:
        return self._by_url.get(normalize_url_before_fetch(url))

    def search(self, query: str, *, limit: int) -> list[dict[str, str]]:
        query_tokens = _tokens(query)
        scored: list[tuple[int, CorpusDocument]] = []
        for document in self._documents:
            haystack = " ".join([document.title, *document.tags, document.body])
            overlap = len(query_tokens & _tokens(haystack))
            if overlap > 0:
                scored.append((overlap, document))
        scored.sort(key=lambda item: (-item[0], item[1].doc_id))
        return [
            {
                "url": normalize_url_before_fetch(document.url),
                "title": document.title,
                "snippet": document.body[:200],
            }
            for _score, document in scored[:limit]
        ]


class CorpusSearch:
    """Async search callable compatible with ``build_research_tool_registry``."""

    def __init__(self, corpus: Corpus, faults: EvalFaults | None = None) -> None:
        self._corpus = corpus
        self._faults = faults or EvalFaults()
        self.calls: list[str] = []

    async def search(self, query: str) -> dict:
        self.calls.append(query)
        if query in self._faults.search_queries:
            return {"ok": False, "error": {"code": "search_failed"}}
        results = self._corpus.search(query, limit=5)
        return {"ok": True, "results": results}


class CorpusFetcher:
    """Async page fetcher served from the local corpus, with optional faults."""

    def __init__(self, corpus: Corpus, faults: EvalFaults | None = None) -> None:
        self._corpus = corpus
        self._faults = faults or EvalFaults()
        self._fetch_faults = {
            normalize_url_before_fetch(url): mode
            for url, mode in self._faults.fetch.items()
        }
        self._attempts: dict[str, int] = {}
        self.calls: list[str] = []

    async def fetch(self, url: str) -> RawDocument:
        self.calls.append(url)
        normalized = normalize_url_before_fetch(url)
        mode = self._fetch_faults.get(normalized)
        attempt = self._attempts.get(normalized, 0)
        self._attempts[normalized] = attempt + 1

        if mode == "raise":
            raise RuntimeError("corpus fetcher exploded")
        if mode == "transient_always" or (mode == "transient_once" and attempt == 0):
            raise WebFetchError("provider_timeout", "simulated timeout")

        document = self._corpus.document_for(normalized)
        failed = mode == "empty" or document is None
        content = "" if failed else (document.body if document else "")
        return RawDocument(
            doc_id=f"doc-{len(self.calls)}",
            requested_url=url,
            final_url=url,
            canonical_url=url,
            title=document.title if document else f"Missing {url}",
            content=content,
            content_hash="sha256:" + hashlib.sha256(content.encode()).hexdigest(),
            fetched_at=FIXED_NOW,
            scraper_used=ScraperUsed.HTTPX_TRAFILATURA,
            status="failed" if failed else "success",
        )


class EvalClock:
    def now(self) -> datetime:
        return FIXED_NOW


class LiveClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class RecordingEventSink:
    def __init__(self, trajectory: TrajectoryRecorder | None = None) -> None:
        self.events: list[tuple[str, dict]] = []
        self._trajectory = trajectory

    async def emit(self, event_type: str, payload: dict) -> None:
        self.events.append((event_type, payload))
        if event_type == "evidence.view" and self._trajectory is not None:
            self._trajectory.record_view(payload)
        if event_type == "agent.tool_observation" and self._trajectory is not None:
            self._trajectory.record_agent_result(payload)


class CountingModelGateway:
    """Wraps a model gateway and records the roles it was asked to play."""

    def __init__(
        self, inner, trajectory: TrajectoryRecorder, *, counter=None, batch_counter=None
    ) -> None:
        self._inner = inner
        self._trajectory = trajectory
        self.roles: list[str] = []
        self._counter = counter
        self._batch_counter = batch_counter
        telemetry = getattr(inner, "telemetry", None)
        self.telemetry = (
            telemetry
            if isinstance(telemetry, ModelTelemetry)
            else ModelTelemetry(provider_instrumented=False)
        )

    async def invoke(self, *, role: str, messages: list, tools=None):
        if self._counter is not None:
            self._counter.reserve(
                *([self._batch_counter] if self._batch_counter else [])
            )
        self.roles.append(role)
        sequence = self._trajectory.record_input(role, messages)
        self._trajectory.record_observations(role, messages)
        index = (
            self.telemetry.start() if not self.telemetry.provider_instrumented else None
        )
        try:
            response = await self._inner.invoke(
                role=role, messages=messages, tools=tools
            )
        except BaseException as exc:
            if index is not None:
                self.telemetry.finish(index, error=exc)
            raise
        if index is not None:
            self.telemetry.finish(index, response)
        self._trajectory.record_model(role, messages, response, sequence=sequence)
        return response


class CountingToolGateway:
    """Wraps the real tool gateway and records every execution request."""

    def __init__(
        self, inner: AgentToolGateway, trajectory: TrajectoryRecorder, *, counter=None
    ) -> None:
        self._inner = inner
        self._trajectory = trajectory
        self.calls: list[dict] = []
        self._counter = counter

    async def execute(self, **kwargs):
        if self._counter is not None:
            self._counter.reserve()
        self.calls.append(kwargs)
        try:
            result = await self._inner.execute(**kwargs)
        except Exception as exc:  # Observe and re-raise the original failure.
            self._trajectory.record_execution(
                kwargs["caller"], kwargs["request"], error=exc
            )
            raise
        self._trajectory.record_execution(kwargs["caller"], kwargs["request"], result)
        return result


@dataclass
class EvalEnvironment:
    context: HarnessContext
    evidence_store: InMemoryEvidenceStore
    budgets: InMemoryBudgetManager
    events: RecordingEventSink
    model_gateway: CountingModelGateway
    tool_gateway: CountingToolGateway
    search: object
    fetcher: object
    trajectory: TrajectoryRecorder

    @property
    def model_calls(self) -> int:
        return len(self.model_gateway.roles)

    @property
    def tool_calls(self) -> int:
        return len(self.tool_gateway.calls)

    def usage_snapshot(self) -> dict:
        usage = self.model_gateway.telemetry.snapshot()
        local = [p for kind, p in self.events.events if kind == "agent.local_tool"]
        record = sum(p["tool"] == "record_findings" and p["executed"] for p in local)
        todos = sum(p["tool"] == "write_todos" and p["executed"] for p in local)
        finish = sum(p["tool"] == "finish_research" and p["executed"] for p in local)
        usage["agent_tools"] = {
            "gateway_calls": self.tool_calls,
            "record_findings_calls": record,
            "write_todos_calls": todos,
            "finish_research_calls": finish,
            "local_skipped": sum(not p["executed"] for p in local),
            "total_executed_calls": self.tool_calls + record + todos + finish,
        }
        return usage

    async def aclose(self) -> None:
        close = getattr(self.fetcher, "aclose", None)
        if close is not None:
            await close()

    @property
    def fetched_pages(self) -> int:
        from deeptrace.domain import ToolName

        return sum(
            1
            for call in self.tool_gateway.calls
            if call["request"].tool is ToolName.FETCH_PAGE
        )


def _budget_scopes(run_id: str) -> list[BudgetScopeKey]:
    caller_ids = (
        "workflow-graph",
        "plan-execute-executor",
        *(f"researcher-{index}" for index in range(6)),
    )
    scopes = [BudgetScopeKey.for_run(run_id)]
    for mode in ResearchMode:
        scopes.append(BudgetScopeKey.for_mode(run_id, mode))
        for caller_id in caller_ids:
            scopes.append(BudgetScopeKey.for_agent(run_id, mode, caller_id))
    return scopes


def build_eval_context(
    corpus: Corpus | None,
    *,
    model_gateway,
    run_id: str,
    faults: EvalFaults | None = None,
    workspace_id: str = "eval-workspace",
    retry_attempts: int = 3,
    retry_base_seconds: float = 0.0,
    limits=None,
    batch_model_counter=None,
    tool_counter=None,
    memory_enabled: bool = True,
    response_max_content_chars: int | None = None,
    search=None,
    fetcher=None,
) -> EvalEnvironment:
    """Assemble a ``HarnessContext`` whose only substitution is search/fetch."""

    live = search is not None or fetcher is not None
    if live:
        if (
            corpus is not None
            or search is None
            or fetcher is None
            or faults is not None
        ):
            raise ValueError("live adapters require both adapters and no corpus/faults")
    elif corpus is None:
        raise ValueError("frozen evaluation requires corpus")
    else:
        search = CorpusSearch(corpus, faults)
        fetcher = CorpusFetcher(corpus, faults)
    evidence_store = InMemoryEvidenceStore()
    registry = build_research_tool_registry(
        search=search.search, fetcher=fetcher, evidence_store=evidence_store
    )

    budgets = InMemoryBudgetManager(
        {scope: DEFAULT_BUDGET for scope in _budget_scopes(run_id)}
    )
    trajectory = TrajectoryRecorder(record_content=True)
    events = RecordingEventSink(trajectory)
    inner_gateway = AgentToolGateway(
        registry=registry,
        allowlist=StaticToolAllowlist(),
        security=DeterministicUrlSecurityPolicy(),
        budgets=budgets,
        executions=InMemoryToolExecutionStore(),
        cache=SuccessCacheSingleflight(InMemorySuccessCache()),
        evidence_store=evidence_store,
        event_sink=events,
        retry_attempts=retry_attempts,
        retry_base_seconds=retry_base_seconds,
    )
    tool_gateway = CountingToolGateway(
        inner_gateway,
        trajectory,
        counter=tool_counter
        if tool_counter is not None
        else (RequestCounter(limits.max_tool_calls) if limits else None),
    )
    counting_model = CountingModelGateway(
        model_gateway,
        trajectory,
        counter=RequestCounter(limits.max_model_calls) if limits else None,
        batch_counter=batch_model_counter,
    )
    context = HarnessContext(
        user_id="eval-user",
        workspace_id=workspace_id,
        model_gateway=counting_model,
        tool_gateway=tool_gateway,
        evidence_store=evidence_store,
        event_sink=events,
        clock=LiveClock() if live else EvalClock(),
        memory_store=InMemoryMemoryStore() if memory_enabled else None,
        response_max_content_chars=response_max_content_chars,
    )
    return EvalEnvironment(
        context=context,
        evidence_store=evidence_store,
        budgets=budgets,
        events=events,
        model_gateway=counting_model,
        tool_gateway=tool_gateway,
        search=search,
        fetcher=fetcher,
        trajectory=trajectory,
    )
