"""The live evaluator must use read anchors and current visible short refs."""

import json

import pytest
from langgraph.runtime import Runtime
from langchain_core.messages import AIMessage

from deeptrace.domain import (
    EvidenceSupport,
    Finding,
    ResearchMode,
    ResearchRequirement,
    ResearchTopicOutcome,
)
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

FACT = "`key`\nnot optional. 🧭"
QUESTION = "Explain Alpha technical context and identifier necessity."


@pytest.mark.asyncio
async def test_schema_repair_keeps_the_exact_original_reference_window():
    from deeptrace.strategies.evidence_evaluation import run_evidence_evaluation
    from deeptrace.strategies.workflow.models import ReferenceWorkflowEvaluation
    from strategies.fixtures import evaluation_payload_from_view
    from strategies.test_reference_materials import seed

    class RepairingModel:
        views = []
        async def available_input_tokens(self, role):
            return 14000 if not self.views else 12000
        async def invoke(self, *, messages, **kwargs):
            material = json.JSONDecoder().raw_decode(str(messages[-1].content).split('EVIDENCE_VIEW_JSON:',1)[1].lstrip())[0]
            self.views.append(material)
            if len(self.views) == 1:
                return AIMessage(content='{"sufficient":"invalid"}')
            return AIMessage(content=json.dumps(evaluation_payload_from_view(str(messages[-1].content), sufficient=True)))

    model = RepairingModel()
    fixture = build_gateway_fixture(model_gateway=model)
    records = [await seed(fixture, i, ('Distinct source original '+str(i)+' cancellation. ') * 200) for i in range(5)]
    await run_evidence_evaluation({'run_id':'run-1','thread_id':'thread-1',
        'question':'Cancellation', 'current_date':'2026-11-18','timezone':'Asia/Shanghai',
        'requirements':[ResearchRequirement(id='r1',description='Cancellation')],
        'evidence_contract_version':3, 'evidence_ids':[r.id for r in records]},
        fixture.context, ReferenceWorkflowEvaluation, repair_attempts=1)
    assert len(model.views) == 2
    assert model.views[0] == model.views[1]


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", list(ResearchMode))
async def test_read_fact_reaches_live_evaluator_and_resolves_without_quote_copy(mode):
    def respond(prompt):
        material = json.JSONDecoder().raw_decode(
            prompt.rsplit("EVIDENCE_VIEW_JSON:", 1)[1].lstrip()
        )[0]
        unit = next(p for p in material["passages"] if p["text"] == FACT)
        payload = {
            "source_checks": [{"source": s["source"], "status": "eligible",
                               "reason": "fixture source"} for s in material["sources"]],
            "findings": [
                {
                    "id": "f1",
                    "claim": "The identifier is required.",
                    "confidence": 0.9,
                    "supports": [{"ref": unit["ref"]}],
                }
            ],
            "coverage": {
                "items": [
                    {
                        "requirement_id": "r1",
                        "status": "covered",
                        "reason": "The raw source explicitly says not optional.",
                        "finding_ids": ["f1"],
                    }
                ]
            },
            "unresolved_gaps": [],
        }
        if mode is ResearchMode.WORKFLOW:
            payload["sufficient"] = True
        else:
            payload.update(action="complete", reason="Supported")
        return json.dumps(payload)

    fixture = build_gateway_fixture(
        model_gateway=ScriptedModelGateway({"evaluator": respond})
    )
    body = ("Alpha technical context identifier. " * 15 + "\n\n") * 30 + FACT
    record = await fixture.evidence_store.ingest(
        TENANT_ID,
        EvidenceDraft(
            canonical_url="https://example.com/anchor",
            title="Anchor",
            media_type="text/plain",
            body=body,
            fetched_at=FIXED_NOW,
            source_quality=0.9,
        ),
    )
    anchor = ReadEvidenceAnchor(
        evidence_id=record.id,
        version=record.version,
        content_hash=record.content_hash,
        start=len(body) - 21,
        end=len(body),
    )
    outcome = ResearchTopicOutcome(
        query="identifier",
        evidence_ids=[record.id],
        read_anchors=[anchor],
        research_findings=[
            Finding(
                id="research-1",
                claim="The identifier is required.",
                confidence=0.9,
                evidence_ids=[record.id],
                supports=[EvidenceSupport(**anchor.model_dump(exclude={"queries"}), quote=FACT)],
            )
        ],
    )
    state = {
        "run_id": "run-1",
        "thread_id": "thread-1",
        "question": QUESTION,
        "current_date": "2026-10-03",
        "timezone": "Asia/Shanghai",
        "evidence_contract_version": 3,
        "requirements": [
            ResearchRequirement(id="r1", description="Explain identifier necessity.")
        ],
        "evidence_ids": [record.id],
        "topic_outcomes": [outcome] if mode is not ResearchMode.MULTI_AGENT else [],
        "researcher_outcomes": [outcome] if mode is ResearchMode.MULTI_AGENT else [],
    }
    node = {
        ResearchMode.PLAN_EXECUTE: evaluate_node,
        ResearchMode.WORKFLOW: workflow_evaluate,
        ResearchMode.MULTI_AGENT: supervisor_evaluate_node,
    }[mode]
    result = await node(state, Runtime(context=fixture.context))
    assert result["coverage"].items[0].status == "covered"
    support = result["findings"][0].supports[0]
    assert support.quote == FACT
    assert (support.start, support.end) == (len(body) - 21, len(body))
    assert body[support.start : support.end] == FACT
    from deeptrace.harness.checkpoint import create_harness_checkpoint_serializer

    serializer = create_harness_checkpoint_serializer()
    assert serializer.loads_typed(serializer.dumps_typed(result)) == result


@pytest.mark.asyncio
async def test_old_midrun_v2_cannot_dispatch_live_evaluation():
    fixture = build_gateway_fixture()
    state = {
        "run_id": "run-1",
        "thread_id": "thread-1",
        "question": QUESTION,
        "current_date": "2026-10-03",
        "timezone": "Asia/Shanghai",
        "evidence_contract_version": 2,
        "requirements": [
            ResearchRequirement(id="r1", description="Explain identifier necessity.")
        ],
    }
    with pytest.raises(ValueError, match="incompatible_evidence_contract"):
        await evaluate_node(state, Runtime(context=fixture.context))
