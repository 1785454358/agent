"""Existing strategy loops close current gaps without erasing diagnostics."""

import json

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver

from deeptrace.domain import CoverageAssessment, EvidenceSupport, Finding, ResearchMode
from deeptrace.harness.agent_executor import build_research_agent_graph
from deeptrace.harness.checkpoint import create_harness_checkpoint_serializer
from deeptrace.strategies import (
    build_multi_agent_research_graph,
    build_plan_execute_research_graph,
    build_workflow_research_graph,
)
from deeptrace.strategies import evidence_evaluation as evaluation
from strategies.fixtures import (
    ScriptedModelGateway,
    build_gateway_fixture,
    evaluation_payload_from_view,
    scripted_research_response,
)


def test_new_support_counts_as_progress_without_a_new_url():
    coverage = CoverageAssessment(
        items=[{"requirement_id": "r1", "status": "missing", "reason": "detail"}]
    )
    support = EvidenceSupport(
        evidence_id="e1", version=1, content_hash="hash", start=50, end=54, quote="fact"
    )
    finding = Finding(
        id="f1", claim="detail", confidence=0.9, evidence_ids=["e1"], supports=[support]
    )
    assert hasattr(evaluation, "progress_keys"), "progress tracking is not implemented"
    before = evaluation.progress_keys([], [], coverage)
    after = evaluation.progress_keys([], [finding], coverage)
    assert after - before == frozenset({'support:["e1",1,"hash",50,54]'})
    assert (
        evaluation.progress_keys(
            [], [finding.model_copy(update={"id": "renamed"})], coverage
        )
        == after
    )


def test_gap_plan_rejects_duplicate_queries_and_non_gap_targets():
    assert hasattr(evaluation, "parse_gap_tasks"), (
        "targeted supplement planning is missing"
    )
    payload = {
        "tasks": [
            {"query": "  CHECKPOINTS   detail ", "target_requirement_ids": ["r2"]},
            {"query": "Store", "target_requirement_ids": []},
            {"query": "Store", "target_requirement_ids": ["r1"]},
            {"query": "Store", "target_requirement_ids": ["r2"]},
            {"query": " STORE ", "target_requirement_ids": ["r2"]},
            {"query": "Store scope", "target_requirement_ids": ["r2"]},
            {"query": "extra", "target_requirement_ids": ["r2"]},
        ]
    }
    tasks = evaluation.parse_gap_tasks(
        payload,
        gap_ids={"r2"},
        requirement_ids={"r1", "r2"},
        dispatched=["checkpoints detail"],
        limit=2,
    )
    assert [(task.query, task.target_requirement_ids) for task in tasks] == [
        ("Store", ["r2"]),
        ("Store scope", ["r2"]),
    ]


FACTS = {
    "Checkpoints": "Checkpoints persist thread state.",
    "Store": "Store shares facts across threads.",
}


def _research_response(prompt, messages):
    tools = [json.loads(m.content) for m in messages if isinstance(m, ToolMessage)]
    if not tools:
        query = "Store" if "当前研究分支：Store" in prompt else "Checkpoints"
        if query == "Store":
            assert "本分支目标需求：r2" in prompt
            assert "r2:missing" in prompt
        return AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "search_web",
                    "args": {"query": query},
                    "id": f"search-{query}",
                }
            ],
        )
    last = tools[-1]
    if last["tool"] == "search_web":
        url = json.loads(last["preview"])["results"][0]["url"]
        return AIMessage(
            content="",
            tool_calls=[{"name": "fetch_page", "args": {"url": url}, "id": "fetch"}],
        )
    if last["tool"] == "fetch_page":
        return AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "read_evidence",
                    "args": {"evidence_id": last["evidence_ids"][0]},
                    "id": "read",
                }
            ],
        )
    assert last["tool"] == "read_evidence" and last["ok"]
    return AIMessage(content="Source read; task finished.")


def _evaluation_response(prompt, mode):
    view = json.JSONDecoder().raw_decode(
        prompt.rsplit("\nEVIDENCE_VIEW_JSON:\n", 1)[1]
    )[0]
    findings, items = [], []
    for index, (name, fact) in enumerate(FACTS.items(), 1):
        passage = next((p for p in view["passages"] if fact in p["text"]), None)
        if passage:
            findings.append(
                {
                    "id": f"f{index}",
                    "claim": fact,
                    "confidence": 0.9,
                    "supports": [{"ref": passage["ref"]}],
                }
            )
        items.append(
            {
                "requirement_id": f"r{index}",
                "status": "covered" if passage else "missing",
                "reason": "literal source" if passage else f"need {name}",
                "finding_ids": [f"f{index}"] if passage else [],
            }
        )
    complete = all(item["status"] == "covered" for item in items)
    result = {"findings": findings, "coverage": {"items": items}, "unresolved_gaps": []}
    result["source_checks"] = [{"source": s["source"], "status": "eligible",
                               "reason": "fixture source"} for s in view["sources"]]
    if mode is ResearchMode.WORKFLOW:
        result["sufficient"] = complete
    else:
        result.update(
            action="complete"
            if complete
            else "replan"
            if mode is ResearchMode.PLAN_EXECUTE
            else "follow_up",
            reason="coverage",
        )
    return json.dumps(result)


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", list(ResearchMode))
async def test_real_mode_graph_targets_store_and_closes_old_gap(mode):
    initial_key = "assignments" if mode is ResearchMode.MULTI_AGENT else "queries"

    def supplement(prompt):
        assert "requirements" in prompt and "r2" in prompt and "need Store" in prompt
        return json.dumps(
            {"tasks": [{"query": "Store", "target_requirement_ids": ["r2"]}]}
        )

    class ReadingGateway(ScriptedModelGateway):
        async def invoke(self, *, role, messages, tools=None):
            if role == "researcher":
                self.calls.append((role, str(messages[-1].content)))
                return _research_response(str(messages[1].content), messages)
            return await super().invoke(role=role, messages=messages, tools=tools)

    model = ReadingGateway(
        {
            "supervisor" if mode is ResearchMode.MULTI_AGENT else "planner": json.dumps(
                {
                    initial_key: ["Checkpoints"],
                    "query_targets": {"Checkpoints": ["r1", "r2"]},
                    "requirements": [
                        {"id": f"r{i}", "description": f"Explain {name}"}
                        for i, name in enumerate(FACTS, 1)
                    ],
                }
            ),
            "evaluator": lambda prompt: _evaluation_response(prompt, mode),
            "replanner"
            if mode is ResearchMode.PLAN_EXECUTE
            else "follow_up": supplement,
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
    factory = {
        ResearchMode.WORKFLOW: build_workflow_research_graph,
        ResearchMode.PLAN_EXECUTE: build_plan_execute_research_graph,
        ResearchMode.MULTI_AGENT: build_multi_agent_research_graph,
    }[mode]
    graph = factory(
        build_research_agent_graph(),
        checkpointer=InMemorySaver(serde=create_harness_checkpoint_serializer()),
    )
    state = {
        "run_id": "run-1",
        "thread_id": "thread-1",
        "question": "Explain Checkpoints and Store",
        "current_date": "2026-10-02",
        "timezone": "Asia/Shanghai",
    }
    result = await graph.ainvoke(
        state,
        config={"configurable": {"thread_id": "progress"}},
        context=fixture.context,
    )
    outcome = result["outcome"]
    if mode is ResearchMode.WORKFLOW:
        assert outcome.termination_reason == "insufficient_evidence"
        assert [i.status for i in outcome.coverage.items] == ["covered", "missing"]
        assert fixture.search.calls == ["Checkpoints"]
    else:
        assert outcome.termination_reason == "completed"
        assert [i.status for i in outcome.coverage.items] == ["covered", "covered"]
        assert outcome.unresolved_gaps == []
        assert fixture.search.calls == ["Checkpoints", "Store"]
        assert any("r2:missing" in gap for gap in result["diagnostic_gaps"])
    assert all(f.supports for f in outcome.findings)


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", [ResearchMode.PLAN_EXECUTE, ResearchMode.MULTI_AGENT])
async def test_cached_source_with_no_new_support_stops_after_a_whole_supplement_batch(
    mode,
):
    key = "assignments" if mode is ResearchMode.MULTI_AGENT else "queries"
    action = "follow_up" if mode is ResearchMode.MULTI_AGENT else "replan"
    model = ScriptedModelGateway(
        {
            "supervisor" if mode is ResearchMode.MULTI_AGENT else "planner": json.dumps(
                {
                    key: ["first"],
                    "query_targets": {"first": ["r1"]},
                    "requirements": [{"id": "r1", "description": "Need detail"}],
                }
            ),
            "evaluator": lambda p: json.dumps(
                evaluation_payload_from_view(p, action=action)
            ),
            "follow_up"
            if mode is ResearchMode.MULTI_AGENT
            else "replanner": json.dumps(
                {
                    "tasks": [
                        {"query": query, "target_requirement_ids": ["r1"]}
                        for query in ["second", "third", "fourth"]
                    ]
                }
            ),
        }
    )
    fixture = build_gateway_fixture(
        model_gateway=model,
        default_search_results=[{"url": "https://example.com/same", "title": "same"}],
        pages={"https://example.com/same": "one unchanged source fact"},
    )
    factory = (
        build_plan_execute_research_graph
        if mode is ResearchMode.PLAN_EXECUTE
        else build_multi_agent_research_graph
    )
    result = await factory(build_research_agent_graph()).ainvoke(
        {
            "run_id": "run-1",
            "thread_id": "thread-1",
            "question": "Need detail",
            "current_date": "2026-10-02",
            "timezone": "UTC",
        },
        context=fixture.context,
    )
    assert result["outcome"].termination_reason == "no_research_progress"
    assert set(fixture.search.calls) == {"first", "second", "third"}
    assert len(fixture.search.calls) == 3
    assert len([r for r, _ in model.calls if r == "evaluator"]) == 2
    assert result["supplement_completed"] and result["no_progress"]
    assert len(result["outcome"].evidence_ids) == 1
    assert len(result["progress_before_supplement"]) <= 256


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", list(ResearchMode))
async def test_empty_initial_search_without_open_todos_can_try_an_alternative(mode):
    key = "assignments" if mode is ResearchMode.MULTI_AGENT else "queries"

    class Gateway(ScriptedModelGateway):
        async def invoke(self, *, role, messages, tools=None):
            if role == "researcher":
                return scripted_research_response(messages, tools)
            return await super().invoke(role=role, messages=messages, tools=tools)

    model = Gateway(
        {
            "supervisor" if mode is ResearchMode.MULTI_AGENT else "planner": json.dumps(
                {
                    key: ["empty"],
                    "query_targets": {"empty": ["r1"]},
                    "requirements": [{"id": "r1", "description": "Explain Store"}],
                }
            ),
            "evaluator": lambda p: json.dumps(
                evaluation_payload_from_view(
                    p, sufficient=True if mode is ResearchMode.WORKFLOW else None
                )
            ),
            "follow_up"
            if mode is ResearchMode.MULTI_AGENT
            else "replanner": json.dumps(
                {"tasks": [{"query": "Store", "target_requirement_ids": ["r1"]}]}
            ),
        }
    )
    fixture = build_gateway_fixture(
        model_gateway=model,
        search_results={
            "Store": [{"url": "https://example.com/store", "title": "Store"}]
        },
        pages={"https://example.com/store": FACTS["Store"]},
    )
    factory = {
        ResearchMode.WORKFLOW: build_workflow_research_graph,
        ResearchMode.PLAN_EXECUTE: build_plan_execute_research_graph,
        ResearchMode.MULTI_AGENT: build_multi_agent_research_graph,
    }[mode]
    result = await factory(build_research_agent_graph()).ainvoke(
        {
            "run_id": "run-1",
            "thread_id": "thread-1",
            "question": "Explain Store",
            "current_date": "2026-10-02",
            "timezone": "UTC",
        },
        context=fixture.context,
    )
    if mode is ResearchMode.WORKFLOW:
        assert result["outcome"].termination_reason == "no_sources"
        assert fixture.search.calls == ["empty"]
    else:
        assert result["outcome"].termination_reason == "completed"
        assert fixture.search.calls == ["empty", "Store"]
        assert result["outcome"].unresolved_gaps == []
