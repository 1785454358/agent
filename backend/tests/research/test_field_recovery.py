from datetime import date

import pytest

from deeptrace.domain import EvidenceSupport, Finding, ResearchRequirement
from deeptrace.domain.research_record import ExperimentRecord, ObservedValue, StudyIdentity
from strategies.fixtures import build_gateway_fixture
from strategies.test_reference_materials import seed


async def case():
    fixture = build_gateway_fixture()
    opening = "Published: 22 January 2025. Model-A on Benchmark-B achieves 71.2."
    protocol = "For Model-A evaluation we sample 64 responses with a maximum length of 4096 tokens."
    body = opening + "\n\n" + "Unrelated background.\n\n" * 200 + protocol
    record = await seed(fixture, 1, body)
    finding = Finding(id="f1", claim="A conditional result", evidence_ids=[record.id], confidence=0.9,
        supports=[EvidenceSupport(evidence_id=record.id, version=record.version,
            content_hash=record.content_hash, start=0, end=len(opening), quote=opening)],
        research_result=StudyIdentity(kind="original_experiment", title="Study A", published_on=date(2025,1,22)),
        experiments=[ExperimentRecord(model=ObservedValue(value="Model-A",support_indices=[0]),
            result=ObservedValue(value="71.2",support_indices=[0]))])
    state = {"run_id":"run-1","thread_id":"thread-1","question":"对比模型结果和计算预算",
        "current_date":"2026-11-17","timezone":"Asia/Shanghai","evidence_contract_version":3,
        "research_brief":{"source_policy":"research_results"},
        "requirements":[ResearchRequirement(id="r1",description="计算预算与结果")],
        "coverage":{"items":[{"requirement_id":"r1","status":"missing","reason":"budget not read","finding_ids":["f1"]}]},
        "evidence_ids":[record.id],"source_eligibility":{record.id:"eligible"},"findings":[finding]}
    return fixture, state, protocol


@pytest.mark.asyncio
async def test_missing_budget_reads_existing_original_before_new_search_and_never_repeats():
    from deeptrace.research.field_recovery import field_reread_node, plan_field_reads
    from langgraph.runtime import Runtime
    fixture, state, protocol = await case()
    plan = await plan_field_reads(state,fixture.context)
    assert len(plan["reread_actions"]) == 1
    result = await field_reread_node(state,Runtime(context=fixture.context))
    anchors = result["topic_outcomes"][0].read_anchors
    assert anchors
    text = await fixture.evidence_store.read_body("workspace-1",anchors[0].evidence_id)
    assert protocol in text[anchors[0].start:anchors[0].end]
    assert all(call["request"].tool.value == "read_evidence" for call in fixture.gateway.calls)
    assert result["field_checks"][0]["status"] == "read_unresolved"
    repeated = await plan_field_reads({**state,**result},fixture.context)
    assert repeated["reread_actions"] == []


@pytest.mark.asyncio
async def test_stale_field_check_does_not_authorize_unknown_or_hide_new_version():
    from deeptrace.research.field_recovery import field_reread_node, plan_field_reads
    from langgraph.runtime import Runtime
    fixture,state,_ = await case()
    result = await field_reread_node(state,Runtime(context=fixture.context))
    checks = [{**check,"content_hash":"sha256:old"} for check in result["field_checks"]]
    plan = await plan_field_reads({**state,"field_checks":checks},fixture.context)
    assert plan["reread_actions"]


@pytest.mark.asyncio
@pytest.mark.parametrize("allow_unknown",[False,True])
async def test_host_does_not_accept_model_complete_when_requested_budget_is_unread(allow_unknown):
    import json
    from dataclasses import replace
    from langchain_core.messages import AIMessage
    from langgraph.runtime import Runtime
    from deeptrace.research.quality import evaluate_node
    fixture,state,_ = await case()
    state["requirements"][0]=state["requirements"][0].model_copy(update={"allow_unknown":allow_unknown})
    class OptimisticEvaluator:
        async def invoke(self, **kwargs):
            view = json.loads(str(kwargs["messages"][-1].content).split("EVIDENCE_VIEW_JSON:\n")[1])
            ref = next(p["ref"] for p in view["passages"] if "71.2" in p["text"])
            date_ref = next(p["ref"] for p in view["passages"] if "Published:" in p["text"])
            return AIMessage(content=json.dumps({"findings":[{"id":"f1","claim":"Model-A achieves 71.2",
                "confidence":0.9,"supports":[{"ref":ref}],"research_result":{"kind":"original_experiment",
                    "title":"Study A","published_on":"2025-01-22","date_refs":[date_ref]},
                "experiments":[{"model":{"value":"Model-A","refs":[ref]},"result":{"value":"71.2","refs":[ref]}}]}],
                "source_checks":[{"source":"s1","status":"eligible","reason":"original"}],
                "coverage":{"items":[{"requirement_id":"r1","status":"covered","reason":"claimed complete","finding_ids":["f1"]}]},
                "sufficient":True}))
    result = await evaluate_node(state,Runtime(context=replace(fixture.context,model_gateway=OptimisticEvaluator())))
    assert result["coverage"].items[0].status == "missing"
    assert not result["verification"].coverage_complete
    assert result["field_actions"]
    from deeptrace.research.field_recovery import field_reread_node
    read = await field_reread_node({**state,**result},Runtime(context=fixture.context))
    assert read["topic_outcomes"][0].read_anchors
    again=await evaluate_node({**state,**result,**read},Runtime(context=replace(fixture.context,model_gateway=OptimisticEvaluator())))
    assert again["verification"].coverage_complete is allow_unknown
    if allow_unknown:
        assert again["coverage"].items[0].resolution=="not_found"
        assert again["coverage"].items[0].limitations
