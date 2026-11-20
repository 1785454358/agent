"""Evaluator policy must remain separate from model-authored planning data."""

import json

import pytest
from langchain_core.messages import AIMessage

from deeptrace.domain import ResearchRequirement, ResearchTopicOutcome
from deeptrace.domain.evidence_anchor import ReadEvidenceAnchor
from deeptrace.strategies.evidence_evaluation import run_evidence_evaluation
from deeptrace.strategies.multi_agent.models import ReferenceSupervisorEvaluation
from deeptrace.tools.evidence_store import EvidenceDraft
from strategies.fixtures import FIXED_NOW, TENANT_ID, build_gateway_fixture


@pytest.mark.asyncio
async def test_evaluator_policy_keeps_user_task_and_excludes_planner_criteria():
    captured = []

    class Gateway:
        async def invoke(self, *, role, messages, **kwargs):
            captured.extend(messages)
            return AIMessage(
                content=json.dumps(
                    {
                        "action": "follow_up",
                        "reason": "No automatic admission",
                        "coverage": {
                            "items": [
                                {
                                    "requirement_id": "r1",
                                    "status": "missing",
                                    "reason": "Needs semantic evaluation",
                                }
                            ]
                        },
                    }
                )
            )

    fixture = build_gateway_fixture(model_gateway=Gateway())
    body = "Restantes tareas canceladas."
    source = await fixture.evidence_store.ingest(
        TENANT_ID,
        EvidenceDraft(
            canonical_url="https://docs.python.org/es/3.11/library/asyncio-task.html",
            title="Python 3.11 official documentation",
            media_type="text/plain",
            body=body,
            fetched_at=FIXED_NOW,
            source_quality=0.9,
        ),
    )
    result = await run_evidence_evaluation(
        {
            "run_id": "run-1",
            "thread_id": "thread-1",
            "current_date": "2026-10-11",
            "timezone": "Asia/Shanghai",
            "question": "仅依据 Python 3.11 官方文档说明取消机制。用中文回答。",
            "conversation_summary": {"user_constraints": ["USER_CONSTRAINT_MARKER"]},
            "evidence_contract_version": 3,
            "requirements": [ResearchRequirement(id="r1", description="说明取消机制")],
            "research_brief": {"scope": "MODEL_SCOPE_MARKER: 中文资料优先"},
            "evidence_ids": [source.id],
            "researcher_outcomes": [
                ResearchTopicOutcome(
                    query="cancel",
                    evidence_ids=[source.id],
                    read_anchors=[
                        ReadEvidenceAnchor(
                            evidence_id=source.id,
                            version=source.version,
                            content_hash=source.content_hash,
                            start=0,
                            end=len(body),
                        )
                    ],
                )
            ],
        },
        fixture.context,
        ReferenceSupervisorEvaluation,
        incomplete_action="follow_up",
    )
    policy = captured[0].content
    data = captured[-1].content
    assert captured[0].type == "system"
    assert "回答语言不等于证据语言" in policy
    assert "原始用户明确" in policy
    assert "MODEL_SCOPE_MARKER" not in policy
    assert "MODEL_SCOPE_MARKER" not in data
    assert "仅依据 Python 3.11 官方文档说明取消机制" in data
    assert "USER_CONSTRAINT_MARKER" in data
    assert "说明取消机制" in data
    assert "Restantes tareas canceladas." in data
    assert result["coverage"].items[0].status == "missing"
    assert result["source_eligibility"][source.id] == "uncertain"
