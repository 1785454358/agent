import json

import pytest
from langchain_core.messages import AIMessage

from deeptrace.domain import ErrorCategory, ResearchRequirement
from deeptrace.domain.evidence_anchor import ReadEvidenceAnchor
from deeptrace.harness.model_budget import RunBudgetModelGateway
from deeptrace.harness.model_gateway import ModelCallError
from deeptrace.strategies.evidence_evaluation import run_evidence_evaluation
from deeptrace.strategies.workflow.models import ReferenceWorkflowEvaluation
from strategies.fixtures import build_gateway_fixture
from strategies.test_reference_materials import seed


@pytest.mark.asyncio
@pytest.mark.parametrize("category,limit,expected_calls,admitted", [
    (ErrorCategory.TRANSIENT, 4, 2, True),
    (ErrorCategory.FATAL, 4, 1, False),
    (ErrorCategory.TRANSIENT, 3, 2, False),
])
async def test_first_assessment_transport_recovery_obeys_shared_budget(category, limit, expected_calls, admitted):
    class Flaky:
        calls = 0
        evaluation_calls = 0
        async def invoke(self, **kwargs):
            self.calls += 1
            if kwargs["role"] == "planner":
                return AIMessage(content="A prior plan")
            self.evaluation_calls += 1
            if self.evaluation_calls == 1:
                raise ModelCallError(category)
            view = json.loads(str(kwargs["messages"][-1].content).split("EVIDENCE_VIEW_JSON:\n")[1])
            ref = view["passages"][0]["ref"]
            return AIMessage(content=json.dumps({"findings": [{"id": "f1", "claim": "A factual result",
                "confidence": 0.9, "supports": [{"ref": ref}]}], "source_checks": [
                {"source": "s1", "status": "eligible", "reason": "relevant original"}],
                "coverage": {"items": [{"requirement_id": "r1", "status": "covered",
                    "finding_ids": ["f1"], "reason": "supported"}]}, "sufficient": True}))
    provider = Flaky()
    gateway = RunBudgetModelGateway(provider, max_calls=limit)
    if limit == 3:
        await gateway.invoke(role="planner", messages=[])
    fixture = build_gateway_fixture(model_gateway=gateway)
    record = await seed(fixture, 1, "An original technical result is explicitly stated.")
    body = await fixture.evidence_store.read_body("workspace-1", record.id)
    state = {"run_id": "run-1", "thread_id": "thread-1", "question": "Explain technical result",
        "current_date": "2026-11-17", "timezone": "Asia/Shanghai", "evidence_contract_version": 3,
        "requirements": [ResearchRequirement(id="r1", description="Explain result")],
        "evidence_ids": [record.id], "read_anchors": [ReadEvidenceAnchor(evidence_id=record.id,
            version=record.version, content_hash=record.content_hash, start=0, end=len(body))]}
    result = await run_evidence_evaluation(state, fixture.context, ReferenceWorkflowEvaluation)
    assert bool(result["findings"]) is admitted
    assert (result["source_eligibility"][record.id] == "eligible") is admitted
    assert gateway.used_calls == expected_calls
    assert provider.calls == expected_calls
