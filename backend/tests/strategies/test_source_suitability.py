"""Current source checks gate real evaluator findings, not just their citations."""

import json

import pytest
from langgraph.runtime import Runtime

from deeptrace.domain import ResearchMode, ResearchRequirement, ResearchTopicOutcome
from deeptrace.domain.evidence_anchor import ReadEvidenceAnchor
from deeptrace.strategies.multi_agent.nodes import supervisor_evaluate_node
from deeptrace.strategies.plan_execute.nodes import evaluate_node
from deeptrace.strategies.workflow.nodes import evaluate_node as workflow_evaluate
from deeptrace.tools.evidence_store import EvidenceDraft
from strategies.fixtures import (
    FIXED_NOW,
    TENANT_ID,
    ScriptedModelGateway,
    build_gateway_fixture,
)


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", list(ResearchMode))
@pytest.mark.parametrize(
    "status", [None, "eligible", "ineligible", "uncertain", "duplicate", "unknown"]
)
async def test_source_check_controls_coverage_and_persisted_admission(mode, status):
    def respond(prompt):
        view = json.JSONDecoder().raw_decode(
            prompt.rsplit("EVIDENCE_VIEW_JSON:", 1)[1].lstrip()
        )[0]
        ref = view["passages"][0]["ref"]
        payload = {
            "findings": [
                {
                    "id": "f1",
                    "claim": "Cleanup is required.",
                    "confidence": 0.9,
                    "supports": [{"ref": ref}],
                }
            ],
            "coverage": {
                "items": [
                    {
                        "requirement_id": "r1",
                        "status": "covered",
                        "reason": "explicit source",
                        "finding_ids": ["f1"],
                    }
                ]
            },
            "unresolved_gaps": [],
        }
        if status is not None:
            checks = [
                {
                    "source": "s2" if status == "unknown" else "s1",
                    "status": "eligible"
                    if status in {"duplicate", "unknown"}
                    else status,
                    "reason": "fixture source scope",
                }
            ]
            payload["source_checks"] = checks * (2 if status == "duplicate" else 1)
        if mode is ResearchMode.WORKFLOW:
            payload["sufficient"] = True
        else:
            payload.update(action="complete", reason="complete")
        return json.dumps(payload)

    fixture = build_gateway_fixture(
        model_gateway=ScriptedModelGateway({"evaluator": respond})
    )
    body = "Cleanup is required."
    record = await fixture.evidence_store.ingest(
        TENANT_ID,
        EvidenceDraft(
            canonical_url="https://example.com/v2/tasks",
            title="v2",
            body=body,
            media_type="text/plain",
            fetched_at=FIXED_NOW,
            source_quality=0.9,
        ),
    )
    anchor = ReadEvidenceAnchor(
        evidence_id=record.id,
        version=record.version,
        content_hash=record.content_hash,
        start=0,
        end=len(body),
    )
    outcome = ResearchTopicOutcome(
        query="cleanup", evidence_ids=[record.id], read_anchors=[anchor]
    )
    state = {
        "run_id": "r",
        "thread_id": "t",
        "question": "Use only v2 official docs; explain cleanup.",
        "current_date": "2026-10-04",
        "timezone": "Asia/Shanghai",
        "evidence_contract_version": 3,
        "requirements": [ResearchRequirement(id="r1", description="Explain cleanup")],
        "evidence_ids": [record.id],
        "topic_outcomes": [] if mode is ResearchMode.MULTI_AGENT else [outcome],
        "researcher_outcomes": [outcome] if mode is ResearchMode.MULTI_AGENT else [],
    }
    node = {
        ResearchMode.PLAN_EXECUTE: evaluate_node,
        ResearchMode.WORKFLOW: workflow_evaluate,
        ResearchMode.MULTI_AGENT: supervisor_evaluate_node,
    }[mode]
    result = await node(state, Runtime(context=fixture.context))
    assert result["coverage"].items[0].status == (
        "covered" if status == "eligible" else "missing"
    )
    assert bool(result["findings"]) == (status == "eligible")
    assert result["source_eligibility"].get(record.id) == (
        status if status in {"eligible", "ineligible"} else "uncertain"
    )
