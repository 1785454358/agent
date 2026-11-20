"""Regressions for failures observed in the Beijing live trial."""

import json

import pytest
from langchain_core.messages import AIMessage

from deeptrace.domain import ResearchRequirement
from deeptrace.research.runtime import build_controller_research_graph
from strategies.fixtures import build_gateway_fixture
from research.test_runtime import CaptureTopic, request


@pytest.mark.asyncio
async def test_invalid_optional_metadata_preserves_complementary_discovery_queries():
    queries = ["City attraction tickets", "City accommodation prices", "City food transport prices"]
    requirements = [
        {"id": "r1", "description": "Attraction prices"},
        {"id": "r2", "description": "Accommodation and food prices"},
    ]

    class Model:
        async def invoke(self, **kwargs):
            return AIMessage(content=json.dumps({
                "queries": queries, "requirements": requirements,
                "query_targets": {queries[0]: ["unplanned"]},
                "research_brief": {"objective": "Incomplete optional metadata"},
            }))

    topic = CaptureTopic()
    result = await build_controller_research_graph(topic, max_rounds=1).ainvoke(
        request().model_dump(), context=build_gateway_fixture(model_gateway=Model()).context)
    assert [task.query for task in topic.requests] == queries
    assert [r.id for r in result["requirements"]] == ["r1", "r2"]
    assert all(task.constraints == ["Use primary sources"] for task in topic.requests)
    assert all(set(task.target_requirement_ids) == {"r1", "r2"} for task in topic.requests)
    assert result["outcome"].termination_reason != "completed"


def test_compound_requirement_with_unanswered_parts_cannot_be_covered():
    from deeptrace.domain import RequirementCoverage
    item = RequirementCoverage.model_validate({
        "requirement_id": "r1", "status": "covered", "finding_ids": ["f1"],
        "reason": "Palace prices found, temple prices still missing",
        "unanswered_parts": ["Temple admission price"],
    })
    assert item.status == "missing"
    assert item.finding_ids == ["f1"]
    assert item.unanswered_parts == ["Temple admission price"]


def test_source_restriction_must_quote_actual_user_input():
    from deeptrace.strategies.evidence_references import ReferenceSourceCheck, normalize_source_checks
    from deeptrace.tools.evidence_views import EvidencePassage
    passage = EvidencePassage(evidence_id="e1", passage_id="p1", version=1,
                             content_hash="hash", start=0, end=12, text="Room 300/day", start_line=1, end_line=1)
    check = ReferenceSourceCheck.model_validate({
        "source": "s1", "status": "ineligible", "reason": "User wants official sources only",
        "basis": "user_restriction", "restriction_quote": "official sources only",
    })
    statuses, diagnostics = normalize_source_checks(
        [check], {"s1": "e1"}, {"p1": passage}, user_texts=["Plan a city trip with estimated prices"],
    )
    assert statuses["e1"] == "uncertain"
    assert any("unauthorized_source_restriction" in issue for issue in diagnostics)


def test_legitimate_source_restriction_is_preserved():
    from deeptrace.strategies.evidence_references import ReferenceSourceCheck, normalize_source_checks
    from deeptrace.tools.evidence_views import EvidencePassage
    passage = EvidencePassage(evidence_id="e1", passage_id="p1", version=1,
                             content_hash="hash", start=0, end=12, text="Room 300/day", start_line=1, end_line=1)
    check = ReferenceSourceCheck.model_validate({
        "source": "s1", "status": "ineligible", "reason": "Outside requested source scope",
        "basis": "user_restriction", "restriction_quote": "official sources only",
    })
    statuses, _ = normalize_source_checks(
        [check], {"s1": "e1"}, {"p1": passage}, user_texts=["Use official sources only"],
    )
    assert statuses["e1"] == "ineligible"


@pytest.mark.asyncio
async def test_default_discovery_task_can_acquire_the_configured_three_sources():
    from deeptrace.harness.batch_research import build_batch_research_graph
    from deeptrace.research.adapters import build_contract_and_plan
    from deeptrace.research.execution import execute_task
    from harness.test_batch_research import BatchModel
    urls = [f"https://example.com/{name}" for name in ("one", "two", "three")]
    fixture = build_gateway_fixture(
        model_gateway=BatchModel(),
        default_search_results=[{"url": url, "title": url} for url in urls],
        pages={url: f"Distinct source {index} contains a fact." for index, url in enumerate(urls)},
    )
    contract, plan = build_contract_and_plan(
        run_id="run-1", question="Compare the evidence", queries=["source facts"],
        requirements=[ResearchRequirement(id="r1", description="Evidence across sources")],
    )
    outcome = await execute_task(
        task=plan.tasks[0], contract=contract, research_input=request(), context=fixture.context,
        topic_graph=build_batch_research_graph(source_target=3), authorized_evidence_ids=[],
    )
    assert len(outcome.evidence_ids) == 3


@pytest.mark.asyncio
async def test_source_selection_repair_can_still_fetch_at_exact_task_model_cap():
    from deeptrace.harness.batch_research import build_batch_research_graph
    from deeptrace.research.execution import execute_task
    from deeptrace.research.adapters import build_contract_and_plan

    class RepairSelector:
        calls = 0

        async def invoke(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return AIMessage(content='{"selected":["unknown"]}')
            return AIMessage(content='{"selected":["c1"],"read_queries":[]}')

    model = RepairSelector()
    fixture = build_gateway_fixture(model_gateway=model,
        search_results={"hotel": [{"url": "https://example.com/hotel", "title": "Hotel"}]},
        pages={"https://example.com/hotel": "A dated room price reference with occupancy conditions."})
    contract, plan = build_contract_and_plan(run_id="run-1", question="Room reference",
        requirements=[ResearchRequirement(id="r1", description="Room reference")], queries=["hotel"])
    outcome = await execute_task(task=plan.tasks[0], contract=contract, research_input=request(),
        context=fixture.context, topic_graph=build_batch_research_graph(), authorized_evidence_ids=[])
    assert model.calls == 2
    assert outcome.evidence_ids
    assert outcome.agent_outcome.stop_reason == "completed"


@pytest.mark.asyncio
@pytest.mark.parametrize("repair_source_admission", [True, False])
async def test_unsupported_source_restriction_is_repaired_even_without_findings(repair_source_admission):
    from deeptrace.domain import ResearchTopicOutcome
    from deeptrace.domain.evidence_anchor import ReadEvidenceAnchor
    from deeptrace.strategies.evidence_evaluation import run_evidence_evaluation
    from deeptrace.strategies.workflow.models import ReferenceWorkflowEvaluation
    from deeptrace.tools.evidence_store import EvidenceDraft

    class Model:
        calls = 0

        async def invoke(self, *, messages, **kwargs):
            self.calls += 1
            view = json.loads(str(messages[-1].content).split("EVIDENCE_VIEW_JSON:\n", 1)[1])
            repaired = self.calls > 1
            return AIMessage(content=json.dumps({
                "source_checks": [{"source": "s1", "status": "eligible" if repaired else "ineligible",
                    "reason": "Dated market reference" if repaired else "Official sources required",
                    "basis": "reliability" if repaired else "user_restriction",
                    "restriction_quote": None if repaired else "Only official hotel prices"}],
                "findings": [{"id": "f1", "claim": "Room reference is 300 per night, date and occupancy apply",
                    "supports": [{"ref": view["passages"][0]["ref"]}], "confidence": 0.8}] if repaired else [],
                "coverage": {"items": [{"requirement_id": "r1", "status": "covered" if repaired else "missing",
                    "reason": "Conditional reference" if repaired else "No official price",
                    "finding_ids": ["f1"] if repaired else []}]},
                "unresolved_gaps": [], "sufficient": repaired,
            }))

    model = Model()
    fixture = build_gateway_fixture(model_gateway=model)
    body = "2026-11-15: a double room reference is 300 per night for two guests; actual booking prices vary."
    record = await fixture.evidence_store.ingest(fixture.context.workspace_id, EvidenceDraft(
        canonical_url="https://example.com/hotel", title="Hotel reference", media_type="text/plain",
        body=body, fetched_at=fixture.context.clock.now(), source_quality=0.7,
    ))
    state = {**request().model_dump(), "question": "Estimate a trip budget with dated market references",
             "conversation_summary": {}, "requirements": [ResearchRequirement(id="r1", description="Room cost reference")],
             "evidence_contract_version": 3, "evidence_ids": [record.id], "topic_outcomes": [ResearchTopicOutcome(
                 query="room", evidence_ids=[record.id], read_anchors=[ReadEvidenceAnchor(
                     evidence_id=record.id, version=record.version, content_hash=record.content_hash, start=0, end=len(body))])],
             "findings": []}
    result = await run_evidence_evaluation(state, fixture.context, ReferenceWorkflowEvaluation,
        repair_attempts=1, repair_source_admission=repair_source_admission)
    assert result["verification"].coverage_complete
    assert result["verification"].accepted_claims
    assert model.calls == 2
