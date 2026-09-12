"""Plan 3 exit gate: Workflow and Response vertical slice, end to end."""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from deeptrace.application.research import (
    ApplicationResearchRequest,
    ExecutionIdentityMismatch,
    ResearchApplicationService,
)
from deeptrace.domain import ResearchMode, ResponseMode
from deeptrace.harness.checkpoint import create_harness_checkpoint_serializer
from deeptrace.harness.graph import build_agent_runtime_graph
from deeptrace.harness.registry import (
    ResponseGraphRegistry,
    ResponseRegistration,
    StrategyRegistration,
    StrategyRegistry,
)
from deeptrace.responses import (
    build_answer_graph,
    build_brief_graph,
    build_report_graph,
)
from deeptrace.strategies import (
    build_research_topic_graph,
    build_workflow_research_graph,
)

from strategies.fixtures import build_gateway_fixture


class ScriptedModelGateway:
    def __init__(self, responses: dict[str, Any]) -> None:
        self._responses = responses
        self.calls: list[tuple[str, str]] = []

    async def invoke(self, *, role: str, messages: list[Any]) -> Any:
        prompt = str(messages[-1].content)
        self.calls.append((role, prompt))
        response = self._responses[role]
        if callable(response):
            response = response(prompt)
        if isinstance(response, Exception):
            raise response
        return response


def _evaluation(prompt: str) -> str:
    ids = sorted(set(re.findall(r"evidence-[0-9a-f]+", prompt)))
    return json.dumps(
        {
            "findings": [
                {
                    "id": "finding-1",
                    "claim": "已获得可用资料",
                    "evidence_ids": ids[:1],
                    "confidence": 0.9,
                }
            ],
            "unresolved_gaps": [],
            "sufficient": True,
        }
    )


def _fixture(model: ScriptedModelGateway):
    return build_gateway_fixture(
        search_results={
            "LangGraph Harness": [
                {"url": "https://example.com/a", "title": "来源 A", "snippet": "s"}
            ]
        },
        pages={"https://example.com/a": "unique-exit-gate-body-marker"},
        model_gateway=model,
    )


def _build_service():
    strategies = StrategyRegistry()
    strategies.register(
        StrategyRegistration(
            ResearchMode.WORKFLOW,
            build_workflow_research_graph(build_research_topic_graph()),
        )
    )
    responses = ResponseGraphRegistry()
    responses.register(
        ResponseRegistration(ResponseMode.ANSWER, build_answer_graph())
    )
    responses.register(
        ResponseRegistration(ResponseMode.BRIEF, build_brief_graph())
    )
    responses.register(
        ResponseRegistration(ResponseMode.REPORT, build_report_graph())
    )
    checkpointer = InMemorySaver(serde=create_harness_checkpoint_serializer())
    graph = build_agent_runtime_graph(
        strategies, responses, checkpointer=checkpointer
    )
    return ResearchApplicationService(graph), checkpointer


def _request(question: str, thread_id: str = "thread-1") -> ApplicationResearchRequest:
    return ApplicationResearchRequest(
        run_id="run-1",
        thread_id=thread_id,
        question=question,
        mode=ResearchMode.WORKFLOW,
    )


def test_exit_gate_default_request_produces_cited_answer_with_typed_tools() -> None:
    model = ScriptedModelGateway(
        {
            "planner": json.dumps({"queries": ["LangGraph Harness"]}),
            "evaluator": _evaluation,
            "responder": json.dumps({"content": "研究结论 [1]。"}),
        }
    )
    fixture = _fixture(model)
    service, checkpointer = _build_service()

    outcome = asyncio.run(
        service.invoke(
            _request("研究 LangGraph Harness"),
            config={"configurable": {"thread_id": "thread-1"}},
            context=fixture.context,
        )
    )

    assert outcome.response_mode is ResponseMode.ANSWER
    assert outcome.partial_reason is None
    assert outcome.content == "研究结论 [1]。"

    # Typed tool calls entered the gateway; page bodies live only in Evidence.
    assert [call["request"].tool.value for call in fixture.gateway.calls] == [
        "search_web",
        "fetch_page",
    ]
    evidence_id = asyncio.run(
        fixture.evidence_store.latest_for_source(
            fixture.context.workspace_id, "https://example.com/a"
        )
    ).id
    assert outcome.cited_evidence_ids == [evidence_id]

    # Private child checkpoints survive under their namespaces.
    async def _namespaces() -> set[str]:
        return {
            item.config["configurable"].get("checkpoint_ns")
            async for item in checkpointer.alist(
                {"configurable": {"thread_id": "thread-1"}}
            )
        }

    namespaces = asyncio.run(_namespaces())
    assert any(ns and ns.startswith("workflow") for ns in namespaces)
    assert any(ns and ns.startswith("answer") for ns in namespaces)
    root = asyncio.run(
        checkpointer.aget_tuple({"configurable": {"thread_id": "thread-1"}})
    )
    assert root is not None
    assert root.config["configurable"]["thread_id"] == "thread-1"


def test_exit_gate_report_request_reuses_research_and_evidence() -> None:
    model = ScriptedModelGateway(
        {
            "planner": json.dumps({"queries": ["LangGraph Harness"]}),
            "evaluator": _evaluation,
            "responder": json.dumps({"content": "# 研究报告\n结论 [1]。"}),
        }
    )
    fixture = _fixture(model)
    service, _checkpointer = _build_service()

    outcome = asyncio.run(
        service.invoke(
            _request("请生成报告"),
            config={"configurable": {"thread_id": "thread-1"}},
            context=fixture.context,
        )
    )

    assert outcome.response_mode is ResponseMode.REPORT
    assert "正式报告" in model.calls[-1][1]
    assert outcome.citations[0].marker == "[1]"


def test_exit_gate_invalid_thread_identity_fails_before_side_effects() -> None:
    model = ScriptedModelGateway({"planner": "unused"})
    fixture = _fixture(model)
    service, _checkpointer = _build_service()

    with pytest.raises(ExecutionIdentityMismatch):
        asyncio.run(
            service.invoke(
                _request("研究"),
                config={"configurable": {"thread_id": "other-thread"}},
                context=fixture.context,
            )
        )

    assert fixture.gateway.calls == []
    assert model.calls == []


def test_exit_gate_legacy_basic_record_reads_as_workflow() -> None:
    from datetime import UTC, datetime

    from deeptrace.runtime.models import RunRecord

    legacy = {
        "id": "legacy-1",
        "question": "旧问题",
        "mode": "basic",
        "status": "completed",
        "created_at": datetime.now(UTC).isoformat(),
    }
    record = RunRecord.model_validate(legacy)
    assert record.mode == "workflow"
