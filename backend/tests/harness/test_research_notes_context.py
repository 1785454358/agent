import pytest

from deeptrace.domain import Finding, EvidenceSupport, ResearchMode
from deeptrace.harness.policies.agent_context import prepare_messages, message_tokens
from deeptrace.harness.token_budget import TokenBudgetConfig
from harness.test_record_findings_loop import seed, task_for
from strategies.fixtures import build_gateway_fixture


@pytest.mark.asyncio
async def test_candidate_notes_are_elastic_untrusted_and_do_not_mutate_state():
    fixture = build_gateway_fixture()
    record, body = await seed(fixture)
    task = task_for(ResearchMode.WORKFLOW, record)
    note = Finding(
        id="research-1",
        claim="UNIQUE_CANDIDATE_CLAIM",
        confidence=0.8,
        evidence_ids=[record.id],
        supports=[
            EvidenceSupport(
                evidence_id=record.id,
                version=record.version,
                content_hash=record.content_hash,
                start=0,
                end=len(body),
                quote=body,
            )
        ],
    )
    state = {"topic_input": task, "research_findings": [note], "messages": []}
    ample = prepare_messages(state, (), TokenBudgetConfig())
    assert note.claim not in ample[1].content
    assert not state["messages"]
    minimal = message_tokens(
        prepare_messages({**state, "research_findings": []}, (), TokenBudgetConfig())
    )
    tight = prepare_messages(
        state,
        (),
        TokenBudgetConfig(
            context_tokens=minimal, output_reserve_tokens=0, safety_tokens=0
        ),
    )
    assert note.claim not in tight[1].content
    assert state["research_findings"] == [note]
