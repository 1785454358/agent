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


@pytest.mark.asyncio
async def test_an_ineligible_new_source_does_not_extend_recovery_as_progress():
    from strategies.test_reference_materials import seed
    fixture = build_gateway_fixture()
    record = await seed(fixture, 1, 'An unrelated out-of-scope page.')
    coverage = CoverageAssessment(items=[{'requirement_id':'r1','status':'missing','reason':'no original'}])
    assert evaluation.progress_keys([record], [], coverage,
        source_eligibility={record.id:'ineligible'}) == evaluation.progress_keys([], [], coverage)


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
