# Agent Harness Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the typed, checkpointable foundation of the LangGraph Harness without changing current API, CLI, Worker, or production research behavior.

**Architecture:** Introduce provider-independent domain contracts, a serializable nested HarnessState with explicit reducers, an immutable Runtime Context, and a registry that binds canonical Profile names to child runnables. Compile a minimal HarnessGraph that initializes a turn, routes to a registered child graph, validates its ResearchOutcome, and finalizes state under an in-memory checkpointer.

**Tech Stack:** Python 3.11+, Pydantic 2, LangGraph 1.x, LangChain Core messages and runnables, pytest, pytest-asyncio.

**Spec:** `docs/superpowers/specs/2026-09-10-langgraph-agent-harness-refactor-design.md`

## Global Constraints

- Canonical Profile values are exactly `workflow`, `plan_execute`, and `multi_agent`.
- `basic` and `deep` are accepted only by the explicit migration normalizer; new state and registry keys always use canonical values.
- The public application still uses the existing `build_real_agent()` path throughout this plan.
- No existing Basic, Deep, Multi-Agent, API, CLI, Runtime, Worker, or persistence implementation is deleted or redirected in this plan.
- Graph State contains only values supported by LangGraph checkpoint serialization.
- Runtime clients and resource owners are represented by Protocols and injected through `HarnessContext`.
- Every task follows red-green-refactor and ends with a focused commit.
- Run all commands from `backend/` unless a step says otherwise.

---

## File Map

### New domain files

- `src/deeptrace/domain/execution.py`: canonical Profile, response, intent, status, budget, error, research input, and research output contracts.
- `src/deeptrace/domain/evidence.py`: typed Finding records that reference Evidence IDs rather than carrying source bodies.
- `src/deeptrace/domain/conversation.py`: bounded structured conversation summary.
- `src/deeptrace/domain/__init__.py`: stable exports for the new domain layer.

### New Harness files

- `src/deeptrace/harness/state.py`: ConversationState, TurnState, reducers, and constructors.
- `src/deeptrace/harness/context.py`: immutable dependency context and provider-independent ports.
- `src/deeptrace/harness/registry.py`: duplicate-safe canonical Profile registry.
- `src/deeptrace/harness/graph.py`: minimal compiled HarnessGraph and registered child invocation adapters.
- `src/deeptrace/harness/__init__.py`: stable Harness exports.

### New tests

- `tests/domain/test_execution.py`
- `tests/domain/test_conversation.py`
- `tests/harness/test_state.py`
- `tests/harness/test_registry.py`
- `tests/harness/test_graph.py`
- `tests/harness/test_public_contracts.py`

## Task 1: Canonical execution contracts

**Files:**
- Create: `backend/src/deeptrace/domain/execution.py`
- Create: `backend/tests/domain/__init__.py`
- Create: `backend/tests/domain/test_execution.py`

**Interfaces:**
- Produces: `ResearchProfile`, `normalize_research_profile`, `ResponseProfile`, `ConversationIntent`, `ExecutionStatus`, `BudgetSnapshot`, `ErrorRecord`, `ResearchInput`, and `ResearchOutcome`.
- Consumes: `Finding` is referenced by forward import only after Task 2; in this task `ResearchOutcome.findings` is typed as `list[dict[str, Any]]`, then Task 2 narrows it to `list[Finding]` in the same Task 2 commit.

- [ ] **Step 1: Write failing canonical-name and model tests**

```python
# tests/domain/test_execution.py
import pytest
from pydantic import ValidationError

from deeptrace.domain.execution import (
    BudgetSnapshot,
    ErrorCategory,
    ExecutionStatus,
    ResearchOutcome,
    ResearchProfile,
    ResponseProfile,
    normalize_research_profile,
)


def test_profile_names_are_canonical_and_legacy_names_only_normalize() -> None:
    assert [item.value for item in ResearchProfile] == [
        "workflow",
        "plan_execute",
        "multi_agent",
    ]
    assert normalize_research_profile("workflow") is ResearchProfile.WORKFLOW
    assert normalize_research_profile("basic") is ResearchProfile.WORKFLOW
    assert normalize_research_profile("deep") is ResearchProfile.PLAN_EXECUTE
    assert normalize_research_profile("multi_agent") is ResearchProfile.MULTI_AGENT
    with pytest.raises(ValueError, match="unknown research profile"):
        normalize_research_profile("agent")


def test_budget_and_outcome_reject_invalid_values() -> None:
    with pytest.raises(ValidationError):
        BudgetSnapshot(max_model_calls=-1)
    with pytest.raises(ValidationError):
        ResearchOutcome(
            profile=ResearchProfile.WORKFLOW,
            evidence_ids=["ev-1", "ev-1"],
            findings=[],
            unresolved_gaps=[],
            executed_steps=1,
            termination_reason="completed",
        )


def test_execution_and_response_values_are_stable() -> None:
    assert ResponseProfile.ANSWER.value == "answer"
    assert ResponseProfile.REPORT.value == "report"
    assert ErrorCategory.AGENT_RECOVERABLE.value == "agent_recoverable"
    assert ExecutionStatus.INTERRUPTED.value == "interrupted"
```

- [ ] **Step 2: Run the tests and verify the module is missing**

Run: `uv run pytest tests/domain/test_execution.py -v`

Expected: FAIL during collection with `ModuleNotFoundError: No module named 'deeptrace.domain'`.

- [ ] **Step 3: Implement the execution contracts**

```python
# src/deeptrace/domain/execution.py
from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class ResearchProfile(StrEnum):
    WORKFLOW = "workflow"
    PLAN_EXECUTE = "plan_execute"
    MULTI_AGENT = "multi_agent"


_LEGACY_PROFILES = {
    "basic": ResearchProfile.WORKFLOW,
    "deep": ResearchProfile.PLAN_EXECUTE,
}


def normalize_research_profile(value: str | ResearchProfile) -> ResearchProfile:
    if isinstance(value, ResearchProfile):
        return value
    candidate = value.strip().lower()
    if candidate in _LEGACY_PROFILES:
        return _LEGACY_PROFILES[candidate]
    try:
        return ResearchProfile(candidate)
    except ValueError as exc:
        raise ValueError(f"unknown research profile: {value}") from exc


class ResponseProfile(StrEnum):
    ANSWER = "answer"
    BRIEF = "brief"
    REPORT = "report"


class ConversationIntent(StrEnum):
    CONVERSATION = "conversation"
    CLARIFICATION = "clarification"
    RESEARCH = "research"
    INCREMENTAL_RESEARCH = "incremental_research"
    SWITCH_PROFILE = "switch_profile"
    REPORT_REQUEST = "report_request"
    MEMORY_UPDATE = "memory_update"


class ExecutionStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    INTERRUPTED = "interrupted"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ErrorCategory(StrEnum):
    TRANSIENT = "transient"
    VALIDATION = "validation"
    POLICY = "policy"
    AGENT_RECOVERABLE = "agent_recoverable"
    PARTIAL = "partial"
    FATAL = "fatal"
    CANCELLED = "cancelled"


class BudgetSnapshot(BaseModel):
    max_model_calls: int = Field(default=0, ge=0)
    max_tool_calls: int = Field(default=0, ge=0)
    max_network_requests: int = Field(default=0, ge=0)
    used_model_calls: int = Field(default=0, ge=0)
    used_tool_calls: int = Field(default=0, ge=0)
    used_network_requests: int = Field(default=0, ge=0)


class ErrorRecord(BaseModel):
    code: str = Field(min_length=1)
    category: ErrorCategory
    retryable: bool = False
    source: str = Field(min_length=1)
    node: str = Field(min_length=1)
    attempt: int = Field(default=1, ge=1)
    public_message: str = Field(min_length=1)
    internal_detail: str | None = None


class ResearchInput(BaseModel):
    question: str = Field(min_length=1)
    conversation_summary: dict[str, Any] = Field(default_factory=dict)
    prior_evidence_ids: list[str] = Field(default_factory=list)
    unresolved_gaps: list[str] = Field(default_factory=list)
    budget: BudgetSnapshot = Field(default_factory=BudgetSnapshot)
    current_date: str
    timezone: str


class ResearchOutcome(BaseModel):
    profile: ResearchProfile
    evidence_ids: list[str] = Field(default_factory=list)
    findings: list[dict[str, Any]] = Field(default_factory=list)
    unresolved_gaps: list[str] = Field(default_factory=list)
    executed_steps: int = Field(ge=0)
    termination_reason: str = Field(min_length=1)

    @field_validator("evidence_ids")
    @classmethod
    def unique_evidence_ids(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("evidence_ids must be unique")
        return value
```

Create an empty `tests/domain/__init__.py` so the test directory is an explicit package.

- [ ] **Step 4: Run the focused tests**

Run: `uv run pytest tests/domain/test_execution.py -v`

Expected: PASS, 3 tests.

- [ ] **Step 5: Commit the contracts**

```powershell
git add src/deeptrace/domain/execution.py tests/domain/__init__.py tests/domain/test_execution.py
git commit -m "feat: add harness execution contracts"
```

## Task 2: Conversation and Evidence domain models

**Files:**
- Create: `backend/src/deeptrace/domain/conversation.py`
- Create: `backend/src/deeptrace/domain/evidence.py`
- Modify: `backend/src/deeptrace/domain/execution.py`
- Create: `backend/src/deeptrace/domain/__init__.py`
- Create: `backend/tests/domain/test_conversation.py`

**Interfaces:**
- Consumes: `ResearchOutcome` from Task 1.
- Produces: `ConversationSummary`, `Finding`, and domain package exports; changes `ResearchOutcome.findings` to `list[Finding]`.

- [ ] **Step 1: Write failing serialization and validation tests**

```python
# tests/domain/test_conversation.py
import pytest
from pydantic import ValidationError

from deeptrace.domain import ConversationSummary, Finding, ResearchOutcome, ResearchProfile


def test_conversation_summary_is_structured_and_bounded() -> None:
    summary = ConversationSummary(
        topic="Agent Harness",
        user_constraints=["默认简洁回答"],
        established_facts=["研究策略与输出策略分离"],
        referenced_entities={"它": "Agent Harness"},
        unresolved_questions=["Checkpoint 存储"],
        previous_conclusions=["采用 HarnessGraph 加子图"],
    )
    assert summary.referenced_entities["它"] == "Agent Harness"
    with pytest.raises(ValidationError):
        ConversationSummary(topic="x", user_constraints=[str(i) for i in range(51)])


def test_research_outcome_contains_findings_by_evidence_reference() -> None:
    outcome = ResearchOutcome(
        profile=ResearchProfile.WORKFLOW,
        evidence_ids=["ev-1"],
        findings=[
            Finding(
                id="finding-1",
                claim="Harness 与 Strategy 分离",
                evidence_ids=["ev-1"],
                confidence=0.9,
            )
        ],
        unresolved_gaps=[],
        executed_steps=3,
        termination_reason="completed",
    )
    assert outcome.findings[0].evidence_ids == ["ev-1"]
    assert "source body" not in outcome.model_dump_json()
```

- [ ] **Step 2: Run the focused tests and verify imports fail**

Run: `uv run pytest tests/domain/test_conversation.py -v`

Expected: FAIL during collection because `ConversationSummary` and `Finding` are not exported.

- [ ] **Step 3: Implement the bounded summary and Finding models**

```python
# src/deeptrace/domain/conversation.py
from pydantic import BaseModel, Field


class ConversationSummary(BaseModel):
    topic: str = ""
    user_constraints: list[str] = Field(default_factory=list, max_length=50)
    established_facts: list[str] = Field(default_factory=list, max_length=100)
    referenced_entities: dict[str, str] = Field(default_factory=dict)
    unresolved_questions: list[str] = Field(default_factory=list, max_length=50)
    previous_conclusions: list[str] = Field(default_factory=list, max_length=50)
```

```python
# src/deeptrace/domain/evidence.py
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
```

Replace the `Any` import and the two provisional fields in `execution.py` with the concrete domain imports and types:

```python
from deeptrace.domain.conversation import ConversationSummary
from deeptrace.domain.evidence import Finding


class ResearchInput(BaseModel):
    question: str = Field(min_length=1)
    conversation_summary: ConversationSummary = Field(
        default_factory=ConversationSummary
    )
    prior_evidence_ids: list[str] = Field(default_factory=list)
    unresolved_gaps: list[str] = Field(default_factory=list)
    budget: BudgetSnapshot = Field(default_factory=BudgetSnapshot)
    current_date: str
    timezone: str


class ResearchOutcome(BaseModel):
    profile: ResearchProfile
    evidence_ids: list[str] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    unresolved_gaps: list[str] = Field(default_factory=list)
    executed_steps: int = Field(ge=0)
    termination_reason: str = Field(min_length=1)

    @field_validator("evidence_ids")
    @classmethod
    def unique_evidence_ids(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("evidence_ids must be unique")
        return value
```

Remove `Any` from `execution.py` after replacing the provisional dictionary fields. Export the domain surface explicitly:

```python
# src/deeptrace/domain/__init__.py
from deeptrace.domain.conversation import ConversationSummary
from deeptrace.domain.evidence import Finding
from deeptrace.domain.execution import (
    BudgetSnapshot,
    ConversationIntent,
    ErrorCategory,
    ErrorRecord,
    ExecutionStatus,
    ResearchInput,
    ResearchOutcome,
    ResearchProfile,
    ResponseProfile,
    normalize_research_profile,
)

__all__ = [
    "BudgetSnapshot",
    "ConversationIntent",
    "ConversationSummary",
    "ErrorCategory",
    "ErrorRecord",
    "ExecutionStatus",
    "Finding",
    "ResearchInput",
    "ResearchOutcome",
    "ResearchProfile",
    "ResponseProfile",
    "normalize_research_profile",
]
```

- [ ] **Step 4: Run both domain test modules**

Run: `uv run pytest tests/domain/test_execution.py tests/domain/test_conversation.py -v`

Expected: PASS, 5 tests.

- [ ] **Step 5: Commit the domain layer**

```powershell
git add src/deeptrace/domain tests/domain
git commit -m "feat: add conversation and evidence contracts"
```

## Task 3: Serializable Harness State and Runtime Context

**Files:**
- Create: `backend/src/deeptrace/harness/state.py`
- Create: `backend/src/deeptrace/harness/context.py`
- Create: `backend/tests/harness/__init__.py`
- Create: `backend/tests/harness/test_state.py`

**Interfaces:**
- Consumes: `ConversationSummary`, `Finding`, `ResearchInput`, `ResearchOutcome`, Profile and status enums.
- Produces: `ConversationState`, `TurnState`, `HarnessState`, `merge_conversation`, `new_conversation`, `new_turn`, provider-independent gateway Protocols, and `HarnessContext`.

- [ ] **Step 1: Write failing reducer, reset, and context tests**

```python
# tests/harness/test_state.py
from dataclasses import FrozenInstanceError

import pytest
from langchain_core.messages import HumanMessage

from deeptrace.domain import ExecutionStatus, ResearchProfile, ResponseProfile
from deeptrace.harness.context import HarnessContext
from deeptrace.harness.state import merge_conversation, new_conversation, new_turn


def test_conversation_reducer_appends_messages_and_replaces_other_fields() -> None:
    initial = new_conversation("thread-1", ResearchProfile.WORKFLOW)
    merged = merge_conversation(
        initial,
        {
            "messages": [HumanMessage(content="继续")],
            "unresolved_gaps": ["国内情况"],
        },
    )
    assert [message.content for message in merged["messages"]] == ["继续"]
    assert merged["active_profile"] is ResearchProfile.WORKFLOW
    assert merged["unresolved_gaps"] == ["国内情况"]


def test_new_turn_does_not_carry_previous_ephemeral_values() -> None:
    turn = new_turn("run-2", "继续研究", ResearchProfile.PLAN_EXECUTE)
    assert turn["status"] is ExecutionStatus.PENDING
    assert turn["response_profile"] is ResponseProfile.ANSWER
    assert turn["research_outcome"] is None
    assert turn["recalled_memory_ids"] == []


def test_harness_context_is_immutable() -> None:
    context = HarnessContext(
        user_id="user-1",
        workspace_id="workspace-1",
        model_gateway=object(),
        tool_gateway=object(),
        evidence_store=object(),
        event_sink=object(),
        clock=object(),
    )
    with pytest.raises(FrozenInstanceError):
        context.user_id = "user-2"
```

- [ ] **Step 2: Run the tests and verify the Harness package is missing**

Run: `uv run pytest tests/harness/test_state.py -v`

Expected: FAIL during collection with `ModuleNotFoundError: No module named 'deeptrace.harness'`.

- [ ] **Step 3: Implement State constructors and the conversation reducer**

```python
# src/deeptrace/harness/state.py
from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

from deeptrace.domain import (
    BudgetSnapshot,
    ConversationIntent,
    ConversationSummary,
    ErrorRecord,
    ExecutionStatus,
    Finding,
    ResearchInput,
    ResearchOutcome,
    ResearchProfile,
    ResponseProfile,
)


class ConversationState(TypedDict):
    thread_id: str
    messages: list[AnyMessage]
    summary: ConversationSummary
    active_profile: ResearchProfile
    user_memory_refs: list[str]
    workspace_memory_refs: list[str]
    evidence_ids: list[str]
    established_findings: list[Finding]
    unresolved_gaps: list[str]
    created_at: str
    updated_at: str
    state_version: int


class TurnState(TypedDict):
    run_id: str
    user_input: str
    intent: ConversationIntent
    selected_profile: ResearchProfile
    response_profile: ResponseProfile
    requires_research: bool
    research_request: ResearchInput | None
    research_outcome: ResearchOutcome | None
    recalled_memory_ids: list[str]
    active_evidence_ids: list[str]
    budget: BudgetSnapshot
    status: ExecutionStatus
    error: ErrorRecord | None


def merge_conversation(
    left: ConversationState, right: dict
) -> ConversationState:
    merged = dict(left)
    if "messages" in right:
        merged["messages"] = list(add_messages(left["messages"], right["messages"]))
    merged.update({key: value for key, value in right.items() if key != "messages"})
    return merged  # type: ignore[return-value]


class HarnessState(TypedDict):
    conversation: Annotated[ConversationState, merge_conversation]
    turn: TurnState


def new_conversation(
    thread_id: str, profile: ResearchProfile
) -> ConversationState:
    now = datetime.now(UTC).isoformat()
    return {
        "thread_id": thread_id,
        "messages": [],
        "summary": ConversationSummary(),
        "active_profile": profile,
        "user_memory_refs": [],
        "workspace_memory_refs": [],
        "evidence_ids": [],
        "established_findings": [],
        "unresolved_gaps": [],
        "created_at": now,
        "updated_at": now,
        "state_version": 1,
    }


def new_turn(run_id: str, user_input: str, profile: ResearchProfile) -> TurnState:
    return {
        "run_id": run_id,
        "user_input": user_input,
        "intent": ConversationIntent.RESEARCH,
        "selected_profile": profile,
        "response_profile": ResponseProfile.ANSWER,
        "requires_research": True,
        "research_request": None,
        "research_outcome": None,
        "recalled_memory_ids": [],
        "active_evidence_ids": [],
        "budget": BudgetSnapshot(),
        "status": ExecutionStatus.PENDING,
        "error": None,
    }
```

- [ ] **Step 4: Implement immutable Runtime Context ports**

```python
# src/deeptrace/harness/context.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class ModelGateway(Protocol):
    async def invoke(self, *, role: str, messages: list[Any]) -> Any: ...


class ToolGateway(Protocol):
    async def execute(self, request: Any) -> Any: ...


class EvidenceStore(Protocol):
    async def get_many(self, evidence_ids: list[str]) -> list[Any]: ...


class EventSink(Protocol):
    async def emit(self, event_type: str, payload: dict[str, Any]) -> None: ...


class Clock(Protocol):
    def now(self) -> Any: ...


@dataclass(frozen=True)
class HarnessContext:
    user_id: str
    workspace_id: str
    model_gateway: ModelGateway
    tool_gateway: ToolGateway
    evidence_store: EvidenceStore
    event_sink: EventSink
    clock: Clock
```

Create an empty `tests/harness/__init__.py`.

- [ ] **Step 5: Run the State tests**

Run: `uv run pytest tests/harness/test_state.py -v`

Expected: PASS, 3 tests.

- [ ] **Step 6: Commit State and Context**

```powershell
git add src/deeptrace/harness/state.py src/deeptrace/harness/context.py tests/harness
git commit -m "feat: add serializable harness state"
```

## Task 4: Canonical Profile Registry

**Files:**
- Create: `backend/src/deeptrace/harness/registry.py`
- Create: `backend/tests/harness/test_registry.py`

**Interfaces:**
- Consumes: `ResearchProfile` and any child object exposing `ainvoke(input, config=None)`.
- Produces: `ProfileGraph`, `ProfileRegistration`, and `ProfileRegistry.register()`, `.resolve()`, and `.profiles()`.

- [ ] **Step 1: Write failing registry behavior tests**

```python
# tests/harness/test_registry.py
import pytest
from langchain_core.runnables import RunnableLambda

from deeptrace.domain import ResearchProfile
from deeptrace.harness.registry import ProfileRegistration, ProfileRegistry


def _graph():
    return RunnableLambda(lambda value: value)


def test_registry_resolves_only_canonical_profile_names() -> None:
    registry = ProfileRegistry()
    registration = ProfileRegistration(ResearchProfile.WORKFLOW, _graph())
    registry.register(registration)
    assert registry.resolve(ResearchProfile.WORKFLOW) is registration
    assert registry.profiles() == (ResearchProfile.WORKFLOW,)
    with pytest.raises(KeyError, match="profile is not registered"):
        registry.resolve(ResearchProfile.PLAN_EXECUTE)


def test_registry_rejects_duplicate_registration() -> None:
    registry = ProfileRegistry()
    registry.register(ProfileRegistration(ResearchProfile.WORKFLOW, _graph()))
    with pytest.raises(ValueError, match="already registered"):
        registry.register(ProfileRegistration(ResearchProfile.WORKFLOW, _graph()))
```

- [ ] **Step 2: Run the test and verify the registry module is missing**

Run: `uv run pytest tests/harness/test_registry.py -v`

Expected: FAIL during collection because `deeptrace.harness.registry` does not exist.

- [ ] **Step 3: Implement the immutable registrations and registry**

```python
# src/deeptrace/harness/registry.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from deeptrace.domain import ResearchProfile


class ProfileGraph(Protocol):
    async def ainvoke(
        self,
        input: dict[str, Any],
        config: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...


@dataclass(frozen=True)
class ProfileRegistration:
    name: ResearchProfile
    graph: ProfileGraph


class ProfileRegistry:
    def __init__(self) -> None:
        self._items: dict[ResearchProfile, ProfileRegistration] = {}

    def register(self, registration: ProfileRegistration) -> None:
        if registration.name in self._items:
            raise ValueError(f"profile already registered: {registration.name.value}")
        self._items[registration.name] = registration

    def resolve(self, name: ResearchProfile) -> ProfileRegistration:
        try:
            return self._items[name]
        except KeyError as exc:
            raise KeyError(f"profile is not registered: {name.value}") from exc

    def profiles(self) -> tuple[ResearchProfile, ...]:
        return tuple(self._items)
```

- [ ] **Step 4: Run the registry tests**

Run: `uv run pytest tests/harness/test_registry.py -v`

Expected: PASS, 2 tests.

- [ ] **Step 5: Commit the registry**

```powershell
git add src/deeptrace/harness/registry.py tests/harness/test_registry.py
git commit -m "feat: add research profile registry"
```

## Task 5: Compiled HarnessGraph skeleton

**Files:**
- Create: `backend/src/deeptrace/harness/graph.py`
- Create: `backend/tests/harness/test_graph.py`

**Interfaces:**
- Consumes: `HarnessState`, `ResearchInput`, `ResearchOutcome`, `ProfileRegistry`, and a LangGraph checkpointer.
- Produces: `build_harness_graph(registry, checkpointer=None)` returning a compiled graph.

- [ ] **Step 1: Write failing end-to-end routing and checkpoint tests**

```python
# tests/harness/test_graph.py
import pytest
from langchain_core.runnables import RunnableLambda
from langgraph.checkpoint.memory import InMemorySaver

from deeptrace.domain import ExecutionStatus, ResearchProfile
from deeptrace.harness.graph import build_harness_graph
from deeptrace.harness.registry import ProfileRegistration, ProfileRegistry
from deeptrace.harness.state import new_conversation, new_turn


def _profile_graph(profile: ResearchProfile):
    return RunnableLambda(
        lambda value: {
            "profile": profile.value,
            "evidence_ids": [f"ev-{profile.value}"],
            "findings": [
                {
                    "id": f"finding-{profile.value}",
                    "claim": f"executed {profile.value}",
                    "evidence_ids": [f"ev-{profile.value}"],
                    "confidence": 1.0,
                }
            ],
            "unresolved_gaps": [],
            "executed_steps": 1,
            "termination_reason": "completed",
        }
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("profile", list(ResearchProfile))
async def test_harness_routes_to_each_registered_profile(profile: ResearchProfile) -> None:
    registry = ProfileRegistry()
    for item in ResearchProfile:
        registry.register(ProfileRegistration(item, _profile_graph(item)))
    graph = build_harness_graph(registry, checkpointer=InMemorySaver())
    thread_id = f"thread-{profile.value}"
    initial = {
        "conversation": new_conversation(thread_id, profile),
        "turn": new_turn("run-1", "研究 Harness", profile),
    }

    result = await graph.ainvoke(
        initial,
        config={"configurable": {"thread_id": thread_id}},
    )

    assert result["turn"]["status"] is ExecutionStatus.COMPLETED
    assert result["turn"]["research_outcome"].profile is profile
    assert result["conversation"]["evidence_ids"] == [f"ev-{profile.value}"]
    snapshot = await graph.aget_state(
        {"configurable": {"thread_id": thread_id}}
    )
    assert snapshot.values["turn"]["run_id"] == "run-1"


@pytest.mark.asyncio
async def test_harness_rejects_an_unregistered_selected_profile() -> None:
    registry = ProfileRegistry()
    registry.register(
        ProfileRegistration(ResearchProfile.WORKFLOW, _profile_graph(ResearchProfile.WORKFLOW))
    )
    graph = build_harness_graph(registry)
    initial = {
        "conversation": new_conversation("thread-1", ResearchProfile.MULTI_AGENT),
        "turn": new_turn("run-1", "研究 Harness", ResearchProfile.MULTI_AGENT),
    }
    with pytest.raises(KeyError, match="profile is not registered"):
        await graph.ainvoke(initial)
```

- [ ] **Step 2: Run the graph tests and verify the graph module is missing**

Run: `uv run pytest tests/harness/test_graph.py -v`

Expected: FAIL during collection because `deeptrace.harness.graph` does not exist.

- [ ] **Step 3: Implement request construction and registered Profile invocation**

```python
# src/deeptrace/harness/graph.py
from __future__ import annotations

from datetime import datetime
from typing import Any

from langgraph.graph import END, START, StateGraph

from deeptrace.domain import ExecutionStatus, ResearchInput, ResearchOutcome, ResearchProfile
from deeptrace.harness.registry import ProfileRegistry
from deeptrace.harness.state import HarnessState


def _route_profile(state: HarnessState) -> str:
    return state["turn"]["selected_profile"].value


def _research_input(state: HarnessState) -> ResearchInput:
    conversation = state["conversation"]
    turn = state["turn"]
    now = datetime.now().astimezone()
    return ResearchInput(
        question=turn["user_input"],
        conversation_summary=conversation["summary"],
        prior_evidence_ids=conversation["evidence_ids"],
        unresolved_gaps=conversation["unresolved_gaps"],
        budget=turn["budget"],
        current_date=now.date().isoformat(),
        timezone=str(now.tzinfo),
    )


def _profile_node(registry: ProfileRegistry, profile: ResearchProfile):
    async def invoke_profile(state: HarnessState) -> dict[str, Any]:
        registration = registry.resolve(profile)
        raw = await registration.graph.ainvoke(_research_input(state).model_dump(mode="json"))
        outcome = ResearchOutcome.model_validate(raw)
        turn = dict(state["turn"])
        turn["research_request"] = _research_input(state)
        turn["research_outcome"] = outcome
        turn["active_evidence_ids"] = list(outcome.evidence_ids)
        return {
            "turn": turn,
            "conversation": {
                "active_profile": profile,
                "evidence_ids": list(
                    dict.fromkeys(
                        state["conversation"]["evidence_ids"] + outcome.evidence_ids
                    )
                ),
                "established_findings": (
                    state["conversation"]["established_findings"] + outcome.findings
                ),
                "unresolved_gaps": list(outcome.unresolved_gaps),
            },
        }

    return invoke_profile


def _initialize_turn(state: HarnessState) -> dict[str, Any]:
    turn = dict(state["turn"])
    turn["status"] = ExecutionStatus.RUNNING
    return {"turn": turn}


def _finalize_turn(state: HarnessState) -> dict[str, Any]:
    turn = dict(state["turn"])
    outcome = turn["research_outcome"]
    turn["status"] = (
        ExecutionStatus.COMPLETED
        if outcome is not None and outcome.termination_reason == "completed"
        else ExecutionStatus.PARTIAL
    )
    return {"turn": turn}


def build_harness_graph(registry: ProfileRegistry, checkpointer=None):
    builder = StateGraph(HarnessState)
    builder.add_node("initialize_turn", _initialize_turn)
    for profile in ResearchProfile:
        builder.add_node(profile.value, _profile_node(registry, profile))
        builder.add_edge(profile.value, "finalize_turn")
    builder.add_node("finalize_turn", _finalize_turn)
    builder.add_edge(START, "initialize_turn")
    builder.add_conditional_edges(
        "initialize_turn",
        _route_profile,
        {profile.value: profile.value for profile in ResearchProfile},
    )
    builder.add_edge("finalize_turn", END)
    return builder.compile(checkpointer=checkpointer)
```

- [ ] **Step 4: Run the graph tests**

Run: `uv run pytest tests/harness/test_graph.py -v`

Expected: PASS, 4 tests.

- [ ] **Step 5: Run all new foundation tests together**

Run: `uv run pytest tests/domain tests/harness -v`

Expected: PASS, 14 tests.

- [ ] **Step 6: Commit the HarnessGraph skeleton**

```powershell
git add src/deeptrace/harness/graph.py tests/harness/test_graph.py
git commit -m "feat: add checkpointable harness graph"
```

## Task 6: Stable package exports and regression gate

**Files:**
- Create: `backend/src/deeptrace/harness/__init__.py`
- Create: `backend/tests/harness/test_public_contracts.py`
- Modify: `backend/tests/test_module_layout.py`

**Interfaces:**
- Consumes: all public foundation types from Tasks 1–5.
- Produces: stable `deeptrace.domain` and `deeptrace.harness` import surfaces without changing the existing root `deeptrace` exports.

- [ ] **Step 1: Write the public import contract test**

```python
# tests/harness/test_public_contracts.py
from deeptrace.domain import (
    ConversationSummary,
    Finding,
    ResearchInput,
    ResearchOutcome,
    ResearchProfile,
    ResponseProfile,
)
from deeptrace.harness import (
    HarnessContext,
    HarnessState,
    ProfileRegistration,
    ProfileRegistry,
    build_harness_graph,
)


def test_foundation_exports_are_stable() -> None:
    assert ResearchProfile.WORKFLOW.value == "workflow"
    assert ResponseProfile.ANSWER.value == "answer"
    assert ConversationSummary.__name__ == "ConversationSummary"
    assert Finding.__name__ == "Finding"
    assert ResearchInput.__name__ == "ResearchInput"
    assert ResearchOutcome.__name__ == "ResearchOutcome"
    assert HarnessContext.__name__ == "HarnessContext"
    assert HarnessState.__name__ == "HarnessState"
    assert ProfileRegistration.__name__ == "ProfileRegistration"
    assert ProfileRegistry.__name__ == "ProfileRegistry"
    assert callable(build_harness_graph)
```

Add these exact imports and assertions to `tests/test_module_layout.py`. Do not remove its existing Basic or Multi-Agent compatibility assertions in this phase.

```python
from deeptrace.domain import ResearchProfile
from deeptrace.harness import ProfileRegistry, build_harness_graph


def test_harness_foundation_interfaces_are_available() -> None:
    assert ResearchProfile.WORKFLOW.value == "workflow"
    assert ResearchProfile.PLAN_EXECUTE.value == "plan_execute"
    assert ResearchProfile.MULTI_AGENT.value == "multi_agent"
    assert ProfileRegistry.__name__ == "ProfileRegistry"
    assert callable(build_harness_graph)
```

- [ ] **Step 2: Run the public contract tests and verify Harness exports are missing**

Run: `uv run pytest tests/harness/test_public_contracts.py tests/test_module_layout.py -v`

Expected: FAIL because `deeptrace.harness.__init__` does not export the requested names.

- [ ] **Step 3: Add explicit Harness exports**

```python
# src/deeptrace/harness/__init__.py
from deeptrace.harness.context import HarnessContext
from deeptrace.harness.graph import build_harness_graph
from deeptrace.harness.registry import ProfileRegistration, ProfileRegistry
from deeptrace.harness.state import HarnessState, new_conversation, new_turn

__all__ = [
    "HarnessContext",
    "HarnessState",
    "ProfileRegistration",
    "ProfileRegistry",
    "build_harness_graph",
    "new_conversation",
    "new_turn",
]
```

Confirm that `src/deeptrace/domain/__init__.py` has an explicit `__all__` containing every symbol imported by the test. Keep the root `src/deeptrace/__init__.py` unchanged so production entrypoints are unaffected.

- [ ] **Step 4: Run foundation and module-layout tests**

Run: `uv run pytest tests/domain tests/harness tests/test_module_layout.py -v`

Expected: PASS.

- [ ] **Step 5: Run the complete non-real regression suite**

Run: `uv run pytest -m "not real"`

Expected: PASS with no external Provider or Tavily calls.

- [ ] **Step 6: Verify import compilation**

Run: `uv run python -m compileall -q src tests`

Expected: exit code 0 with no output.

- [ ] **Step 7: Review the foundation diff**

Run: `git diff --check && git status --short`

Expected: no whitespace errors; only the files listed by this plan are modified or untracked, apart from pre-existing user changes that remain unstaged.

- [ ] **Step 8: Commit the public foundation**

```powershell
git add src/deeptrace/domain src/deeptrace/harness tests/domain tests/harness tests/test_module_layout.py
git commit -m "test: lock harness foundation contracts"
```

## Foundation Exit Gate

Before starting Plan 2, verify all of the following:

- `workflow`, `plan_execute`, and `multi_agent` are the only canonical Profile values.
- Legacy name conversion occurs only through `normalize_research_profile()`.
- Harness State can be checkpointed by `InMemorySaver`.
- Registered child graph state does not become part of HarnessState.
- Research results cross the boundary only through `ResearchOutcome`.
- Runtime dependencies are absent from serialized State.
- Current API, CLI, Worker, and three production modes still run through their existing entrypoints.
- The complete non-real test suite and `compileall` pass.
