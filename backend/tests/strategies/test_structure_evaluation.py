"""Focus selection must reach the production evaluator, not just a helper."""

import json

import pytest
from langgraph.runtime import Runtime

from deeptrace.domain import EvidenceSupport, ResearchMode, ResearchRequirement
from deeptrace.harness.checkpoint import create_harness_checkpoint_serializer
from deeptrace.strategies.evidence_evaluation import assemble_evaluation_view
from deeptrace.strategies.multi_agent.nodes import supervisor_evaluate_node
from deeptrace.strategies.plan_execute.nodes import evaluate_node
from deeptrace.strategies.workflow.nodes import evaluate_node as workflow_evaluate
from deeptrace.tools.evidence_store import EvidenceDraft
from deeptrace.tools.evidence_views import (
    select_evidence_passages,
    select_supported_passages,
)
from strategies.fixtures import (
    FIXED_NOW,
    TENANT_ID,
    ScriptedModelGateway,
    build_gateway_fixture,
)

ALPHA = "Alpha aperture voltage amperage circuitry reliability density thermal drift."
BETA = "Beta lease does not permit redistribution."
QUESTION = "Explain Alpha aperture voltage amperage circuitry reliability density thermal drift."
REQUIREMENTS = [
    ResearchRequirement(id="r1", description=ALPHA),
    ResearchRequirement(id="r2", description="Explain Beta lease"),
]
BODY = (
    ((ALPHA + " ") * 8 + "\n\n") * 12
    + "Ordinary contract background. " * 20
    + BETA
    + "\n\n"
)


async def source(fixture):
    return await fixture.evidence_store.ingest(
        TENANT_ID,
        EvidenceDraft(
            canonical_url="https://example.com/contracts",
            title="Contracts",
            media_type="text/plain",
            body=BODY,
            fetched_at=FIXED_NOW,
            source_quality=0.9,
        ),
    )


@pytest.mark.asyncio
async def test_evaluation_view_keeps_secondary_requirement_whole():
    fixture = build_gateway_fixture()
    record = await source(fixture)
    view = await assemble_evaluation_view(
        fixture.context,
        question=QUESTION,
        requirements=REQUIREMENTS,
        evidence_ids=[record.id],
        findings=[],
    )
    assert any(BETA in p.text for p in view.passages)
    assert any(ALPHA in p.text for p in view.passages)
    assert sum(len(p.text) for p in view.passages) <= 3000
    assert all(p.text == BODY[p.start : p.end] for p in view.passages)
    assert await fixture.evidence_store.read_body(TENANT_ID, record.id) == BODY


@pytest.mark.asyncio
async def test_accepted_quote_has_priority_over_new_focus():
    fixture = build_gateway_fixture()
    record = await source(fixture)
    start = BODY.index(BETA)
    support = EvidenceSupport(
        evidence_id=record.id,
        version=record.version,
        content_hash=record.content_hash,
        start=start,
        end=start + len(BETA),
        quote=BETA,
    )
    passages = select_supported_passages(
        record,
        BODY,
        [support],
        question="Alpha aperture",
        limit=200,
        focus_queries=["Alpha aperture"],
    )
    assert any(BETA in p.text for p in passages)
    assert sum(len(p.text) for p in passages) <= 200
    forged = support.model_copy(update={"content_hash": "wrong"})
    passages = select_supported_passages(
        record,
        BODY,
        [forged],
        question="Alpha aperture",
        limit=200,
        focus_queries=["Alpha aperture"],
    )
    assert all(BETA not in p.text for p in passages)


@pytest.mark.asyncio
async def test_explicit_start_is_not_overridden_by_focus():
    fixture = build_gateway_fixture()
    record = await source(fixture)
    passages = select_evidence_passages(
        record, BODY, query=None, start=17, limit=53, focus_queries=["Beta lease"]
    )
    assert [(p.start, p.end, p.text) for p in passages] == [(17, 70, BODY[17:70])]


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", list(ResearchMode))
async def test_both_facts_reach_actual_three_mode_evaluator(mode):
    def respond(prompt):
        assert QUESTION in prompt
        material = json.JSONDecoder().raw_decode(
            prompt.split("EVIDENCE_VIEW_JSON:", 1)[1].lstrip()
        )[0]
        findings = []
        for index, fact in enumerate([ALPHA, BETA], 1):
            matching = [p for p in material["passages"] if fact in p["text"]]
            assert matching, f"missing whole fact: {fact}"
            # The literal appears repeatedly in Alpha; quote the complete visible
            # paragraph if short enough, otherwise keep only the unique Beta support.
            if index == 1:
                continue
            passage = matching[0]
            findings.append(
                {
                    "id": "f2",
                    "claim": fact,
                    "confidence": 0.9,
                    "supports": [{"ref": passage["ref"]}],
                }
            )
        payload = {
            "source_checks": [{"source": s["source"], "status": "eligible",
                               "reason": "fixture source"} for s in material["sources"]],
            "findings": findings,
            "coverage": {
                "items": [
                    {
                        "requirement_id": "r1",
                        "status": "missing",
                        "reason": "No unique Alpha quote supplied",
                        "finding_ids": [],
                    },
                    {
                        "requirement_id": "r2",
                        "status": "covered",
                        "reason": "Exact Beta lease restriction",
                        "finding_ids": ["f2"],
                    },
                ]
            },
            "unresolved_gaps": [],
        }
        if mode is ResearchMode.WORKFLOW:
            payload["sufficient"] = False
        else:
            payload.update(
                action="complete", reason="Beta supported; Alpha still requires support"
            )
        return json.dumps(payload)

    fixture = build_gateway_fixture(
        model_gateway=ScriptedModelGateway({"evaluator": respond})
    )
    record = await source(fixture)
    state = {
        "run_id": "run-1",
        "thread_id": "thread-1",
        "question": QUESTION,
        "current_date": "2026-10-03",
        "timezone": "Asia/Shanghai",
        "evidence_contract_version": 3,
        "requirements": REQUIREMENTS,
        "evidence_ids": [record.id],
    }
    node = {
        ResearchMode.PLAN_EXECUTE: evaluate_node,
        ResearchMode.WORKFLOW: workflow_evaluate,
        ResearchMode.MULTI_AGENT: supervisor_evaluate_node,
    }[mode]
    result = await node(state, Runtime(context=fixture.context))
    assert [(x.requirement_id, x.status) for x in result["coverage"].items] == [
        ("r1", "missing"),
        ("r2", "covered"),
    ]
    assert BETA in result["findings"][0].supports[0].quote
    support = result["findings"][0].supports[0]
    assert BODY[support.start : support.end] == support.quote
    serializer = create_harness_checkpoint_serializer()
    assert serializer.loads_typed(serializer.dumps_typed(result)) == result
