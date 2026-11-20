"""Planning directions must survive sealing and reach the right consumer."""

import copy
import json
from datetime import UTC, datetime

import pytest
from langgraph.runtime import Runtime

from deeptrace.domain import ResearchMode, ResearchTopicOutcome
from deeptrace.harness.checkpoint import create_harness_checkpoint_serializer
from deeptrace.strategies.evidence_evaluation import seal_initial_plan
from deeptrace.strategies.model_io import branch_context
from deeptrace.strategies.multi_agent.nodes import (
    build_researcher_node,
    route_researchers,
)
from deeptrace.strategies.plan_execute.nodes import build_execute_task_node
from deeptrace.strategies.workflow.nodes import build_research_topic_node, route_topics
from deeptrace.tools.evidence_store import EvidenceDraft
from strategies.fixtures import build_gateway_fixture
from strategies.test_minimal_planning_contract import PLANNERS, run_planner

QUESTION = "2026年量子力学领域进展"
QUERIES = [
    "2026 quantum many-body physics experimental advances",
    "2026 quantum information research papers",
]
BRIEF = {
    "objective": "梳理代表性量子研究成果及其意义和限制",
    "scope": "全球；2026-01-01 至 2026-10-06 已公开研究；按发表时间归类",
    "assumptions": ["未指定地区，按全球代表性成果综述；不是穷尽全部成果"],
    "answer_expectation": "按方向给出具体成果、日期、原始来源与适用限制",
}
TASKS = {
    QUERIES[0]: {
        "objective": "量子多体与量子模拟的代表性成果",
        "boundary": "只研究多体物理；不重复量子计算硬件",
        "source_strategy": "优先论文与研究机构原始发布；检索英文术语",
        "expected_output": "多体成果、原始论文、日期、创新点与限制",
    },
    QUERIES[1]: {
        "objective": "量子信息处理与网络的代表性成果",
        "boundary": "只研究信息处理与网络；不将投资和未来路线图当成果",
        "source_strategy": "原始论文；区分预印本与已发表研究",
        "expected_output": "信息处理成果、原始论文、日期与实验条件",
    },
}


def payload():
    return {
        "requirements": [
            {"id": "r4", "description": "代表性多体成果"},
            {"id": "r2", "description": "代表性信息处理成果"},
        ],
        "query_targets": {QUERIES[0]: ["r4"], QUERIES[1]: ["r2"]},
        "research_brief": copy.deepcopy(BRIEF),
        "task_briefs": copy.deepcopy(TASKS),
    }


def test_sealed_brief_preserves_scope_and_normalizes_task_keys():
    data = payload()
    data["task_briefs"][" " + QUERIES[0] + " "] = data["task_briefs"].pop(QUERIES[0])
    queries, contract = seal_initial_plan(QUESTION, data, QUERIES)
    assert queries == QUERIES
    assert contract["research_brief"] == BRIEF
    assert contract["task_briefs"] == TASKS
    assert contract["query_targets"] == {QUERIES[0]: ["r1"], QUERIES[1]: ["r2"]}
    assert contract["decomposition_degraded"] is False
    serializer = create_harness_checkpoint_serializer()
    assert serializer.loads_typed(serializer.dumps_typed(contract)) == contract


def test_explicit_search_queries_can_align_descriptive_task_labels_without_losing_scope():
    data = payload()
    data["research_brief"]["source_domains"] = ["docs.python.org"]
    for query in QUERIES:
        data["task_briefs"][query]["search_queries"] = [query]
    queries, contract = seal_initial_plan(QUESTION, data, ["Research many-body", "Research information"])
    assert queries == QUERIES
    assert contract["decomposition_degraded"] is False
    assert contract["research_brief"]["source_domains"] == ["docs.python.org"]
    assert contract["query_targets"] == {QUERIES[0]: ["r1"], QUERIES[1]: ["r2"]}
    assert "initial_queries_aligned" in contract["diagnostic_gaps"]


@pytest.mark.parametrize("problem", ["missing_search_query", "conflicting_keys", "extra_task"])
def test_descriptive_label_alignment_requires_unambiguous_validated_mapping(problem):
    data = payload()
    for query in QUERIES:
        data["task_briefs"][query]["search_queries"] = [query]
    if problem == "missing_search_query":
        data["task_briefs"][QUERIES[0]]["search_queries"] = ["different query"]
    elif problem == "conflicting_keys":
        data["query_targets"]["different query"] = data["query_targets"].pop(QUERIES[0])
    else:
        data["task_briefs"]["extra query"] = data["task_briefs"][QUERIES[0]]
    queries, contract = seal_initial_plan(QUESTION, data, ["Research many-body", "Research information"])
    assert queries == [QUESTION]
    assert contract["decomposition_degraded"] is True


@pytest.mark.parametrize(
    "failure",
    [
        "missing_brief",
        "missing_tasks",
        "wrong_query",
        "duplicate_key",
        "blank_goal",
        "oversized",
        "authority",
    ],
)
def test_invalid_brief_cannot_silently_narrow_the_plan(failure):
    data = payload()
    if failure == "missing_brief":
        del data["research_brief"]
    elif failure == "missing_tasks":
        del data["task_briefs"]
    elif failure == "wrong_query":
        data["task_briefs"]["unplanned"] = data["task_briefs"].pop(QUERIES[0])
    elif failure == "duplicate_key":
        data["task_briefs"][" " + QUERIES[0]] = data["task_briefs"][QUERIES[0]]
    elif failure == "blank_goal":
        data["task_briefs"][QUERIES[0]]["objective"] = " "
    elif failure == "oversized":
        data["research_brief"]["scope"] = "x" * 601
    else:
        data["research_brief"]["max_pages"] = 100
    queries, contract = seal_initial_plan(QUESTION, data, QUERIES)
    assert queries == [QUESTION]
    assert contract["decomposition_degraded"] is True
    assert not contract.get("task_briefs")
    if failure in {"missing_tasks", "wrong_query", "duplicate_key", "blank_goal"}:
        assert contract.get("research_brief") == BRIEF
    else:
        assert not contract.get("research_brief")
    assert "initial_research_brief_degraded" in contract["diagnostic_gaps"]


def test_ambiguous_task_mapping_keeps_valid_global_source_hints():
    data = payload()
    data["research_brief"].update(source_domains=["docs.python.org"], publication_years=[2026])
    queries, contract = seal_initial_plan(QUESTION, data, ["Combined prose assignment"])
    assert queries == [QUESTION] and contract["decomposition_degraded"]
    assert contract["task_briefs"] == {}
    assert contract["research_brief"]["source_domains"] == ["docs.python.org"]
    assert contract["research_brief"]["publication_years"] == [2026]


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", list(ResearchMode))
async def test_real_planner_retains_brief_in_one_call(mode):
    _, _, query_field, state_key = PLANNERS[mode]
    data = {**payload(), query_field: QUERIES}
    result, _, _ = await run_planner(mode, 3, json.dumps(data))
    assert result[state_key] == QUERIES
    assert result["research_brief"] == BRIEF
    assert result["task_briefs"] == TASKS


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", list(ResearchMode))
async def test_branch_receives_only_its_directions_and_original_constraints(mode):
    _, contract = seal_initial_plan(QUESTION, payload(), QUERIES)
    state = {
        **contract,
        "run_id": "run-1",
        "thread_id": "thread-1",
        "question": QUESTION,
        "current_date": "2026-10-06",
        "timezone": "Asia/Shanghai",
        "conversation_summary": {"user_constraints": ["用中文回答"]},
        "queries": QUERIES,
        "assignments": QUERIES,
        "current_task": QUERIES[0],
    }
    observed = []

    class Branch:
        async def ainvoke(self, data, config=None):
            task = data["topic_input"]
            observed.append(task)
            return {"outcome": ResearchTopicOutcome(query=task.query)}

    fixture = build_gateway_fixture()
    if mode is ResearchMode.PLAN_EXECUTE:
        await build_execute_task_node(Branch())(
            state, Runtime(context=fixture.context), {}
        )
    else:
        route, build = (
            (route_topics, build_research_topic_node)
            if mode is ResearchMode.WORKFLOW
            else (route_researchers, build_researcher_node)
        )
        await build(Branch())(route(state)[0].arg, Runtime(context=fixture.context), {})
    task = observed[0]
    notes = "\n".join(task.context_notes)
    assert BRIEF["scope"] in notes
    assert TASKS[QUERIES[0]]["objective"] in notes
    assert TASKS[QUERIES[0]]["expected_output"] in notes
    assert TASKS[QUERIES[1]]["objective"] not in notes
    assert task.original_task == QUESTION and task.constraints == ["用中文回答"]
    assert task.target_requirement_ids == ["r1"]


def test_supplement_keeps_global_scope_without_stale_initial_directions():
    _, contract = seal_initial_plan(QUESTION, payload(), QUERIES)
    notes = branch_context(
        {
            **contract,
            "question": QUESTION,
            "query": "2026 quantum foundations experiments",
            "target_requirement_ids": ["r1"],
        }
    )["context_notes"]
    assert BRIEF["scope"] in "\n".join(notes)
    assert TASKS[QUERIES[0]]["boundary"] not in "\n".join(notes)




@pytest.mark.asyncio
async def test_legacy_batch_synthesis_consumes_branch_scope_alongside_real_passages():
    from harness.test_batch_research import BatchModel, graph

    from deeptrace.domain import ResearchTopicInput

    model = BatchModel()
    fixture = build_gateway_fixture(
        model_gateway=model,
        default_search_results=[{"url": "https://example.com/paper", "title": "paper"}],
        pages={"https://example.com/paper": "A limited research finding."},
    )
    _, contract = seal_initial_plan(QUESTION, payload(), QUERIES)
    task = ResearchTopicInput(
        run_id="run-1",
        thread_id="thread-1",
        query=QUERIES[0],
        mode=ResearchMode.PLAN_EXECUTE,
        caller_id="plan-execute-executor",
        **branch_context(
            {
                **contract,
                "question": QUESTION,
                "query": QUERIES[0],
                "target_requirement_ids": ["r1"],
            }
        ),
    )
    # v3 hands actual reads directly to the parent; historical contracts still
    # support branch synthesis with the same bounded scope and original text.
    task = task.model_copy(update={"evidence_contract_version": 2})
    result = await graph().ainvoke({"topic_input": task}, context=fixture.context)
    assert result["outcome"].research_findings
    assert len(model.calls) == 1
    view = json.JSONDecoder().raw_decode(
        str(model.calls[0][1][-1].content).split("BATCH_EVIDENCE_JSON:\n", 1)[1]
    )[0]
    assert BRIEF["scope"] in "\n".join(view["context_notes"])
    assert TASKS[QUERIES[0]]["expected_output"] in "\n".join(view["context_notes"])


@pytest.mark.asyncio
async def test_supplement_planning_receives_scope_and_only_current_gap():
    from deeptrace.domain import CoverageAssessment
    from deeptrace.strategies.evidence_evaluation import supplement_plan
    from strategies.fixtures import ScriptedModelGateway

    model = ScriptedModelGateway(
        {
            "replanner": json.dumps(
                {
                    "tasks": [
                        {
                            "query": "2026 quantum foundations experiments",
                            "target_requirement_ids": ["r1"],
                        }
                    ]
                }
            )
        }
    )
    fixture = build_gateway_fixture(model_gateway=model)
    _, contract = seal_initial_plan(QUESTION, payload(), QUERIES)
    state = {
        **contract,
        "run_id": "run-1",
        "thread_id": "thread-1",
        "question": QUESTION,
        "current_date": "2026-10-06",
        "timezone": "Asia/Shanghai",
        "coverage": CoverageAssessment(
            items=[
                {
                    "requirement_id": "r1",
                    "status": "missing",
                    "reason": "need more evidence",
                },
                {
                    "requirement_id": "r2",
                    "status": "covered",
                    "reason": "supported",
                    "finding_ids": ["f2"],
                },
            ]
        ),
    }
    result = await supplement_plan(
        state, fixture.context, role="replanner", dispatched=QUERIES, limit=2
    )
    assert result["supplement_targets"] == {
        "2026 quantum foundations experiments": ["r1"]
    }
    assert len(model.calls) == 1 and BRIEF["scope"] in model.calls[0][1]
