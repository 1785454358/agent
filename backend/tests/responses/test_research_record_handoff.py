import json

import pytest

from deeptrace.domain import EvidenceSupport, Finding
from deeptrace.domain.research_record import ExperimentRecord, ObservedValue
from deeptrace.responses.evidence import assemble_response_materials
from responses.test_supported_findings import _case
from responses.test_graph import _seed_evidence
from strategies.fixtures import TENANT_ID


@pytest.mark.asyncio
async def test_experiment_conditions_survive_intro_quotes_in_writer_and_audit_materials():
    payload, _, fixture, _ = await _case()
    prefix = ("Overview and generic contribution.\n\n" * 100)[:2000]
    protocol = "Model-R1 | MATH-500 | 97.3. Maximum length 32,768 tokens. Temperature 0.6."
    body = prefix + "\n\n" + "Unrelated prose.\n\n" * 500 + protocol
    ids = await _seed_evidence(fixture.evidence_store, [("https://example.com/experiment", "Study", body)])
    record = await fixture.evidence_store.get(TENANT_ID, ids[0])
    ranges = [(a, a+500) for a in range(0, 2000, 500)] + [(body.index(protocol), len(body))]
    supports = [EvidenceSupport(evidence_id=record.id, version=record.version,
        content_hash=record.content_hash, start=a, end=b, quote=body[a:b]) for a, b in ranges]
    finding = Finding(id="f1", claim="A conditional result", evidence_ids=ids, confidence=0.9,
        supports=supports, experiments=[ExperimentRecord(
            model=ObservedValue(value="Model-R1", support_indices=[4]),
            result=ObservedValue(value="97.3", support_indices=[4]),
            budget=ObservedValue(value="32,768 tokens", support_indices=[4]),
            conditions=ObservedValue(value="Temperature 0.6", support_indices=[4]))])
    payload.research_outcome.findings = [finding]
    payload.research_outcome.evidence_ids = ids
    for limit in (1000, 2000):
        materials = await assemble_response_materials(fixture.context, payload, [record], limit,
            max_support_chars=min(500, limit))
        assert protocol in materials.sources[0]
        assert '"experiments"' in materials.sources[0]
        assert '"value": "97.3"' in materials.sources[0]
        assert '"value": "Temperature 0.6"' in materials.sources[0]


def test_visible_records_omit_forged_values_and_dropped_conditions():
    from deeptrace.research.observations import visible_research_records
    from deeptrace.tools.evidence_views import EvidencePassage
    text = "Model-A scored 71.2."
    support = EvidenceSupport(evidence_id="paper-a", version=1, content_hash="sha256:a",
        start=0, end=len(text), quote=text)
    finding = Finding(id="f1", claim="Candidate", evidence_ids=["paper-a"], confidence=0.9,
        supports=[support], experiments=[ExperimentRecord(
            model=ObservedValue(value="Model-A", support_indices=[0]),
            result=ObservedValue(value="99.9", support_indices=[0]),
            conditions=ObservedValue(value="unknown", support_indices=[1]))])
    visible = {"[1]": [EvidencePassage("paper-a", 1, "sha256:a", "p1", 0, len(text), 1, 1, text)]}
    data = visible_research_records([finding], visible)
    assert data[0]["experiments"][0]["model"]["value"] == "Model-A"
    assert "99.9" not in json.dumps(data)
    assert "unknown" not in json.dumps(data)


@pytest.mark.asyncio
async def test_final_report_table_uses_records_even_when_writer_and_reviewer_mix_scores():
    from dataclasses import replace
    from langchain_core.messages import AIMessage
    from deeptrace.domain import ResponseMode
    from deeptrace.domain.research_record import StudyIdentity
    from deeptrace.responses.graph import build_report_graph
    payload, _, fixture, _ = await _case()
    pages = [("https://example.com/a", "Study A", "Model-A | Dataset-A | 71.0 | during training"),
             ("https://example.com/b", "Study B", "Model-B | Dataset-B | 83.2 | fixed samples")]
    ids = await _seed_evidence(fixture.evidence_store, pages)
    findings = []
    for index, (identity, (_, title, body)) in enumerate(zip(ids, pages), 1):
        record = await fixture.evidence_store.get(TENANT_ID, identity)
        fields = body.split(" | ")
        findings.append(Finding(id=f"f{index}", claim="An experimental result", evidence_ids=[identity], confidence=0.9,
            supports=[EvidenceSupport(evidence_id=identity, version=record.version, content_hash=record.content_hash,
                start=0, end=len(body), quote=body)],
            research_result=StudyIdentity(kind="original_experiment", title=title, published_on="2025-01-22"),
            experiments=[ExperimentRecord(**{name: ObservedValue(value=value, support_indices=[0])
                for name, value in zip(("model", "dataset", "result", "conditions"), fields)})]))
    payload.response_mode = ResponseMode.REPORT
    payload.active_evidence_ids = ids
    payload.research_outcome.evidence_ids = ids
    payload.research_outcome.findings = findings
    class IncorrectTable:
        async def invoke(self, *, role, messages, tools=None):
            value = {"content": "比较如下。\n\n| 模型 | 结果 |\n|---|---|\n| Wrong | 99.9 [1] |\n\n分析依据 [2]。"}
            if "ANSWER_REVIEW_JSON:" in str(messages[-1].content):
                value.update(issues=[], unanswered_points=[])
            return AIMessage(content=json.dumps(value))
    result = await build_report_graph().ainvoke({"response_input": payload}, context=replace(
        fixture.context, model_gateway=IncorrectTable(), response_fact_review=True))
    content = result["outcome"].content
    assert "99.9" not in content
    assert "71.0" in content and "83.2" in content
    assert "during training" in content and "fixed samples" in content
