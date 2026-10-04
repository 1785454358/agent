"""Initial responsibility must cover every sealed requirement without guessing."""

import pytest
from deeptrace.domain import ResearchMode, ResearchTopicOutcome
from deeptrace.strategies.evidence_evaluation import seal_initial_plan
from deeptrace.strategies.multi_agent.nodes import route_researchers
from deeptrace.strategies.plan_execute.nodes import build_execute_task_node
from deeptrace.strategies.workflow.nodes import route_topics
from langgraph.runtime import Runtime

from strategies.fixtures import build_gateway_fixture


def payload(mapping):
    return {
        "requirements": [
            {"id": "r4", "description": "first fact"},
            {"id": "r3", "description": "second fact"},
        ],
        "query_targets": mapping,
    }


def test_targets_follow_sealed_requirement_renumbering():
    queries, contract = seal_initial_plan(
        "full task", payload({" a ": ["r4"], "b": ["r3"]}), ["a", "b"]
    )
    assert queries == ["a", "b"]
    assert contract.get("query_targets") == {"a": ["r1"], "b": ["r2"]}
    assert contract["decomposition_degraded"] is False


@pytest.mark.parametrize(
    "mapping",
    [
        None,
        {},
        {"a": ["r4"]},
        {"a": ["r4"], "b": ["r4"]},
        {"a": ["r4"], "b": ["r7"]},
        {"a": ["r4", "r4"], "b": ["r3"]},
        {"a": ["r4"], "b": []},
        {"a": ["r4"], "b": ["r3"], "extra": ["r4"]},
        {"a": ["r4"], " a ": ["r4"], "b": ["r3"]},
    ],
)
def test_bad_mapping_retains_requirements_in_one_full_question_branch(mapping):
    queries, contract = seal_initial_plan("full task", payload(mapping), ["a", "b"])
    assert queries == ["full task"]
    assert contract["decomposition_degraded"] is True
    assert [r.description for r in contract["requirements"]] == [
        "first fact",
        "second fact",
    ]
    assert contract.get("query_targets") == {"full task": ["r1", "r2"]}


def test_duplicate_requirement_ids_cannot_be_silently_remapped():
    data = payload({"a": ["r4"], "b": ["r4"]})
    data["requirements"][1]["id"] = "r4"
    queries, contract = seal_initial_plan("full task", data, ["a", "b"])
    assert queries == ["full task"]
    assert contract["decomposition_degraded"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", list(ResearchMode))
@pytest.mark.parametrize("supplement", [False, True])
async def test_three_modes_pass_only_assigned_targets(mode, supplement):
    _, contract = seal_initial_plan(
        "full task", payload({"a": ["r4"], "b": ["r3"]}), ["a", "b"]
    )
    state = {
        **contract,
        "run_id": "run-1",
        "thread_id": "thread-1",
        "question": "full task",
        "current_date": "2026-10-03",
        "timezone": "Asia/Shanghai",
        "queries": ["a"],
        "assignments": ["a"],
        "current_task": "a",
    }
    if supplement:
        state["supplement_targets"] = {"a": ["r2"]}
    expected = ["r2"] if supplement else ["r1"]
    if mode is ResearchMode.WORKFLOW:
        assert route_topics(state)[0].arg["target_requirement_ids"] == expected
    elif mode is ResearchMode.MULTI_AGENT:
        assert route_researchers(state)[0].arg["target_requirement_ids"] == expected
    else:
        observed = []

        class Branch:
            async def ainvoke(self, data, config=None):
                task = data["topic_input"]
                observed.append(task.target_requirement_ids)
                return {"outcome": ResearchTopicOutcome(query=task.query)}

        fixture = build_gateway_fixture()
        await build_execute_task_node(Branch())(
            state, Runtime(context=fixture.context), {}
        )
        assert observed == [expected]
