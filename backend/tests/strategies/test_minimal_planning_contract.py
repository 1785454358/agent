"""Delivered planning contract; existing parsing and sealing remain authoritative."""

import json

import pytest
from langchain_core.messages import AIMessage
from langgraph.runtime import Runtime

from deeptrace.domain import ResearchMode
from deeptrace.harness.checkpoint import create_harness_checkpoint_serializer
from deeptrace.strategies.model_io import branch_context
from deeptrace.strategies.multi_agent.nodes import build_supervisor_plan_node
from deeptrace.strategies.plan_execute.nodes import build_plan_node
from deeptrace.strategies.workflow.nodes import build_plan_queries_node
from strategies.fixtures import build_gateway_fixture

QUESTION = "From supplied documentation, compare Alpha, Beta, Gamma and Delta."
QUERIES = ["Alpha release date", "Beta license", "Gamma supported OS", "Delta formats"]
REQUIREMENTS = [
    {"id": "r1", "description": "When was Alpha released?"},
    {"id": "r2", "description": "What is Beta's license?"},
    {"id": "r3", "description": "Which OS does Gamma support?"},
    {"id": "r4", "description": "Which formats does Delta support?"},
]
PLANNERS = {
    ResearchMode.PLAN_EXECUTE: (build_plan_node, "planner", "queries", "plan_tasks"),
    ResearchMode.WORKFLOW: (build_plan_queries_node, "planner", "queries", "queries"),
    ResearchMode.MULTI_AGENT: (
        build_supervisor_plan_node,
        "supervisor",
        "assignments",
        "assignments",
    ),
}


async def run_planner(mode, limit, response):
    """Only replace the external model; invoke production node and real context."""
    factory, _, _, _ = PLANNERS[mode]
    state = {
        "run_id": "run-1",
        "thread_id": "thread-1",
        "question": QUESTION,
        "current_date": "2026-10-03",
        "timezone": "Asia/Shanghai",
        "conversation_summary": {"user_constraints": ["only supplied documentation"]},
    }

    class CaptureModel:
        delivered = None

        async def invoke(self, *, role: str, messages, tools=None):
            assert role == PLANNERS[mode][1]
            assert tools is None
            self.delivered = "\n".join(str(m.content) for m in messages)
            return AIMessage(content=response)

    model = CaptureModel()
    fixture = build_gateway_fixture(model_gateway=model)
    result = await factory(limit)(state, Runtime(context=fixture.context))
    assert model.delivered is not None
    return result, model.delivered, state


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", list(ResearchMode))
@pytest.mark.parametrize("limit,preferred", [(1, "1-1"), (2, "1-2"), (6, "1-3")])
async def test_actual_planner_receives_minimal_coverage_contract(
    mode, limit, preferred
):
    _, _, query_key, state_key = PLANNERS[mode]
    result, prompt, state = await run_planner(
        mode,
        limit,
        json.dumps({query_key: [QUERIES[0]], "requirements": [REQUIREMENTS[0]], "query_targets": {QUERIES[0]: ["r1"]}}),
    )
    assert result[state_key] == ["Alpha release date"]
    assert QUESTION in prompt and "only supplied documentation" in prompt
    assert branch_context({**state, **result})["original_task"] == QUESTION
    assert f"优先{preferred}条" in prompt
    for rule in (
        "最少互补查询",
        "上限不是应凑满",
        "一个查询可覆盖多个",
        "合并同一事实",
        "必要事实边界",
        "不自行添加",
        "过程动作",
        "事实核查",
        "不得为了减少分支丢弃",
    ):
        assert rule in prompt


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", list(ResearchMode))
async def test_four_legal_independent_questions_are_not_hard_capped_to_three(mode):
    _, _, query_key, state_key = PLANNERS[mode]
    result, _, state = await run_planner(
        mode,
        4,
        json.dumps({query_key: QUERIES, "requirements": REQUIREMENTS, "query_targets": {q: [r["id"]] for q, r in zip(QUERIES, REQUIREMENTS, strict=True)}}),
    )
    assert result[state_key] == [
        "Alpha release date",
        "Beta license",
        "Gamma supported OS",
        "Delta formats",
    ]
    assert [r.id for r in result["requirements"]] == ["r1", "r2", "r3", "r4"]
    assert [r.description for r in result["requirements"]] == [
        "When was Alpha released?",
        "What is Beta's license?",
        "Which OS does Gamma support?",
        "Which formats does Delta support?",
    ]
    assert result["decomposition_degraded"] is False
    assert result["evidence_contract_version"] == 3
    assert branch_context({**state, **result})["constraints"] == [
        "only supplied documentation"
    ]
    serializer = create_harness_checkpoint_serializer()
    assert serializer.loads_typed(serializer.dumps_typed(result)) == result


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", list(ResearchMode))
@pytest.mark.parametrize("failure", ["invalid_json", "invalid_constraints"])
async def test_invalid_initial_plan_keeps_existing_whole_task_fallback(mode, failure):
    _, _, query_key, state_key = PLANNERS[mode]
    response = (
        "not JSON"
        if failure == "invalid_json"
        else json.dumps(
            {
                query_key: QUERIES,
                "requirements": REQUIREMENTS,
                "execution_constraints": [" "],
            }
        )
    )
    result, prompt, state = await run_planner(mode, 4, response)
    assert result[state_key] == [QUESTION]
    assert result["decomposition_degraded"] is True
    assert [r.id for r in result["requirements"]] == ["r1"]
    assert QUESTION in prompt
    context = branch_context({**state, **result})
    assert context["original_task"] == QUESTION
    assert context["constraints"] == ["only supplied documentation"]


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", list(ResearchMode))
async def test_legacy_metadata_omission_does_not_degrade_valid_plan(mode):
    _, _, query_key, state_key = PLANNERS[mode]
    result, _, _ = await run_planner(
        mode,
        2,
        json.dumps({query_key: [QUERIES[0]], "requirements": [REQUIREMENTS[0]], "query_targets": {QUERIES[0]: ["r1"]}}),
    )
    assert result[state_key] == ["Alpha release date"]
    assert result["decomposition_degraded"] is False
    assert "execution_constraints" not in result
