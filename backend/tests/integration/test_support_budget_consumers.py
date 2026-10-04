"""Exercise the real evaluator and Writer boundaries, not a replacement view."""

import json

import pytest
from langgraph.runtime import Runtime
from responses.test_graph import ScriptedModelGateway as WriterModel
from responses.test_graph import _response_input
from strategies.fixtures import (
    FIXED_NOW,
    TENANT_ID,
    ScriptedModelGateway,
    build_gateway_fixture,
)

from deeptrace.domain import (
    CoverageAssessment,
    EvidenceSupport,
    Finding,
    ResearchMode,
    ResearchRequirement,
)
from deeptrace.responses.graph import build_answer_graph, build_report_graph
from deeptrace.strategies.multi_agent.nodes import supervisor_evaluate_node
from deeptrace.strategies.plan_execute.nodes import evaluate_node
from deeptrace.strategies.workflow.nodes import evaluate_node as workflow_evaluate
from deeptrace.tools.evidence_store import EvidenceDraft


async def seed(fixture):
    quotes = [(f"FACT-{i}: 中\n`🧭" + str(i) * 500)[:500] for i in range(6)]
    body = "unused prefix\n" * 100 + ("_" * 300).join(quotes) + "_" * 500
    record = await fixture.evidence_store.ingest(
        TENANT_ID,
        EvidenceDraft(
            canonical_url="https://example.com/core-budget",
            title="Cores",
            media_type="text/plain",
            body=body,
            fetched_at=FIXED_NOW,
            source_quality=0.9,
        ),
    )
    findings = [
        Finding(
            id=f"f{i}",
            claim=f"Accepted fact {i}",
            evidence_ids=[record.id],
            confidence=0.9,
            supports=[
                EvidenceSupport(
                    evidence_id=record.id,
                    version=record.version,
                    content_hash=record.content_hash,
                    start=body.index(quote),
                    end=body.index(quote) + 500,
                    quote=quote,
                )
            ],
        )
        for i, quote in enumerate(quotes)
    ]
    requirements = [
        ResearchRequirement(id=f"r{i + 1}", description=f"Explain fact {i}")
        for i in range(6)
    ]
    return record, findings, requirements


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", list(ResearchMode))
async def test_all_accepted_cores_reach_actual_live_evaluator(mode):
    def respond(prompt):
        material = json.JSONDecoder().raw_decode(
            prompt.rsplit("EVIDENCE_VIEW_JSON:", 1)[1].lstrip()
        )[0]
        drafts = []
        for i in range(6):
            units = [p for p in material["passages"] if f"FACT-{i}:" in p["text"]]
            assert len(units) == 1, f"necessary fact {i} was crowded out"
            assert len(units[0]["text"]) == 500
            drafts.append(
                {
                    "id": f"f{i}",
                    "claim": f"Accepted fact {i}",
                    "confidence": 0.9,
                    "supports": [{"ref": units[0]["ref"]}],
                }
            )
        payload = {
            "source_checks": [{"source": s["source"], "status": "eligible",
                               "reason": "fixture source"} for s in material["sources"]],
            "findings": drafts,
            "coverage": {
                "items": [
                    {
                        "requirement_id": f"r{i + 1}",
                        "status": "covered",
                        "reason": "literal",
                        "finding_ids": [f"f{i}"],
                    }
                    for i in range(6)
                ]
            },
            "unresolved_gaps": [],
        }
        if mode is ResearchMode.WORKFLOW:
            payload["sufficient"] = True
        else:
            payload.update(action="complete", reason="all supported")
        return json.dumps(payload)

    fixture = build_gateway_fixture(
        model_gateway=ScriptedModelGateway({"evaluator": respond})
    )
    record, findings, requirements = await seed(fixture)
    state = {
        "run_id": "run-budget",
        "thread_id": "thread-budget",
        "question": "Explain the facts",
        "current_date": "2026-10-03",
        "timezone": "Asia/Shanghai",
        "evidence_contract_version": 3,
        "requirements": requirements,
        "evidence_ids": [record.id],
        "findings": findings,
        "topic_outcomes": [],
        "researcher_outcomes": [],
    }
    node = {
        ResearchMode.PLAN_EXECUTE: evaluate_node,
        ResearchMode.WORKFLOW: workflow_evaluate,
        ResearchMode.MULTI_AGENT: supervisor_evaluate_node,
    }[mode]
    result = await node(state, Runtime(context=fixture.context))
    assert len(result["findings"]) == 6
    assert all(i.status == "covered" for i in result["coverage"].items)


@pytest.mark.asyncio
@pytest.mark.parametrize("builder", [build_answer_graph, build_report_graph])
@pytest.mark.parametrize("version", [2, 3])
async def test_writer_keeps_every_core_that_fits(builder, version):
    model = WriterModel({"responder": json.dumps({"content": "Supported facts [1]."})})
    fixture = build_gateway_fixture(model_gateway=model)
    record, findings, requirements = await seed(fixture)
    payload = _response_input([record.id], question="Explain the facts")
    payload.research_outcome = payload.research_outcome.model_copy(
        update={
            "evidence_contract_version": version,
            "requirements": requirements,
            "findings": findings,
            "coverage": CoverageAssessment(
                items=[
                    {
                        "requirement_id": f"r{i + 1}",
                        "status": "covered",
                        "reason": "literal",
                        "finding_ids": [f"f{i}"],
                    }
                    for i in range(6)
                ]
            ),
        }
    )
    result = await builder().ainvoke(
        {"response_input": payload}, context=fixture.context
    )
    for finding in findings:
        assert finding.claim in model.calls[0][1]
        assert finding.supports[0].quote in model.calls[0][1]
    assert result["outcome"].partial_reason is None


@pytest.mark.asyncio
async def test_genuinely_over_budget_writer_still_remains_partial():
    model = WriterModel({"responder": json.dumps({"content": "Supported facts [1]."})})
    fixture = build_gateway_fixture(model_gateway=model)
    record, findings, requirements = await seed(fixture)
    extra = findings[0].model_copy(
        update={
            "id": "extra",
            "claim": "Extra fact",
            "supports": [
                findings[0]
                .supports[0]
                .model_copy(
                    update={
                        "start": 0,
                        "end": 500,
                        "quote": ("unused prefix\n" * 100)[:500],
                    }
                )
            ],
        }
    )
    payload = _response_input([record.id], question="Explain the facts")
    payload.research_outcome = payload.research_outcome.model_copy(
        update={
            "evidence_contract_version": 3,
            "requirements": requirements,
            "findings": findings + [extra],
            "coverage": CoverageAssessment(
                items=[
                    {
                        "requirement_id": f"r{i + 1}",
                        "status": "covered",
                        "reason": "literal",
                        "finding_ids": [f"f{i}"],
                    }
                    for i in range(6)
                ]
            ),
        }
    )
    result = await build_answer_graph().ainvoke(
        {"response_input": payload}, context=fixture.context
    )
    assert "Extra fact" not in model.calls[0][1]
    assert result["outcome"].partial_reason == "response_evidence_context_limit"
