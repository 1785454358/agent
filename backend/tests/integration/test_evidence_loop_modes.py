"""Three real strategy graphs × Answer/Report; no live services or gold input."""

import json

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from strategies.fixtures import ScriptedModelGateway, build_gateway_fixture
from strategies.test_evidence_progress import (
    FACTS,
    _evaluation_response,
    _research_response,
)

from deeptrace.application.research import (
    ApplicationResearchRequest,
    ResearchApplicationService,
)
from deeptrace.domain import ResearchMode, ResponseMode
from deeptrace.harness.agent_executor import build_research_agent_graph
from deeptrace.harness.checkpoint import create_harness_checkpoint_serializer
from deeptrace.harness.graph import build_agent_runtime_graph
from deeptrace.harness.registry import (
    ResponseGraphRegistry,
    ResponseRegistration,
    StrategyRegistration,
    StrategyRegistry,
)
from deeptrace.responses import build_answer_graph, build_report_graph
from deeptrace.strategies import (
    build_multi_agent_research_graph,
    build_plan_execute_research_graph,
    build_workflow_research_graph,
)


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", list(ResearchMode))
@pytest.mark.parametrize("response_mode", [ResponseMode.ANSWER, ResponseMode.REPORT])
async def test_real_application_keeps_strategy_coverage_and_response_status_consistent(
    mode, response_mode
):
    class ReadingGateway(ScriptedModelGateway):
        async def invoke(self, *, role, messages, tools=None):
            if role == "researcher":
                return _research_response(str(messages[1].content), messages)
            return await super().invoke(role=role, messages=messages, tools=tools)

    model = ReadingGateway(
        {
            "supervisor" if mode is ResearchMode.MULTI_AGENT else "planner": json.dumps(
                {
                    "assignments" if mode is ResearchMode.MULTI_AGENT else "queries": [
                        "Checkpoints"
                    ],
                    "query_targets": {"Checkpoints": ["r1", "r2"]},
                    "requirements": [
                        {"id": f"r{i}", "description": f"Explain {name}"}
                        for i, name in enumerate(FACTS, 1)
                    ],
                }
            ),
            "evaluator": lambda p: _evaluation_response(p, mode),
            "replanner"
            if mode is ResearchMode.PLAN_EXECUTE
            else "follow_up": json.dumps(
                {"tasks": [{"query": "Store", "target_requirement_ids": ["r2"]}]}
            ),
            "responder": json.dumps({"content": "本轮结论可追溯到资料 [1]。"}),
        }
    )
    fixture = build_gateway_fixture(
        model_gateway=model,
        search_results={
            name: [{"url": f"https://example.com/{name.lower()}", "title": name}]
            for name in FACTS
        },
        pages={
            f"https://example.com/{name.lower()}": fact for name, fact in FACTS.items()
        },
    )
    factories = {
        ResearchMode.WORKFLOW: build_workflow_research_graph,
        ResearchMode.PLAN_EXECUTE: build_plan_execute_research_graph,
        ResearchMode.MULTI_AGENT: build_multi_agent_research_graph,
    }
    strategies, responses = StrategyRegistry(), ResponseGraphRegistry()
    strategies.register(
        StrategyRegistration(mode, factories[mode](build_research_agent_graph()))
    )
    responses.register(
        ResponseRegistration(
            response_mode,
            build_answer_graph()
            if response_mode is ResponseMode.ANSWER
            else build_report_graph(),
        )
    )
    graph = build_agent_runtime_graph(
        strategies,
        responses,
        checkpointer=InMemorySaver(serde=create_harness_checkpoint_serializer()),
    )
    question = "Explain Checkpoints and Store" + (
        "，以正式报告形式" if response_mode is ResponseMode.REPORT else ""
    )
    config = {"configurable": {"thread_id": "thread-1"}}
    result = await ResearchApplicationService(graph).invoke(
        ApplicationResearchRequest(
            run_id="run-1", thread_id="thread-1", question=question, mode=mode
        ),
        config=config,
        context=fixture.context,
    )
    snapshot = await graph.aget_state(config)
    outcome = snapshot.values["turn"]["research_outcome"]
    prompt = next(p for role, p in model.calls if role == "responder")
    assert "Explain Checkpoints" in prompt and "Explain Store" in prompt
    assert FACTS["Checkpoints"] in prompt
    assert result.response_outcome.response_mode is response_mode
    if mode is ResearchMode.WORKFLOW:
        assert result.status == "partial"
        assert result.response_outcome.partial_reason == "insufficient_evidence"
        assert "need Store" in prompt
    else:
        assert result.status == "completed"
        assert outcome.unresolved_gaps == []
        assert FACTS["Store"] in prompt
    assert all(f.supports for f in outcome.findings)
    assert set(result.response_outcome.cited_evidence_ids) <= set(outcome.evidence_ids)
    # Reading is a tool operation, never an additional fetched page.
    assert sum(
        c["request"].tool.value == "read_evidence" for c in fixture.gateway.calls
    ) == len(outcome.evidence_ids)
