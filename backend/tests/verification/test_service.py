from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from deeptrace.models import Claim, EvidenceAssessment, VerificationIssue
from deeptrace.verification import (
    RuleCheckResult,
    VerifierAgent,
    merge_verdict,
)


@pytest.fixture
def claim() -> Claim:
    return Claim(
        claim_id="claim-01",
        task_id="task-01",
        section_id="section-01",
        text="关键事实",
        kind="factual",
        importance="key",
        evidence_ids=["ev-support", "ev-refute"],
    )


def test_support_and_refute_become_conflicted(claim) -> None:
    result = merge_verdict(
        claim=claim,
        rules=RuleCheckResult(
            eligible_evidence_ids=["ev-support", "ev-refute"],
            source_identities=["example.com", "another.org"],
        ),
        assessments=[
            EvidenceAssessment(
                evidence_id="ev-support",
                relation="supports",
                reason="直接支持",
            ),
            EvidenceAssessment(
                evidence_id="ev-refute",
                relation="refutes",
                reason="直接反驳",
            ),
        ],
        provider_error=None,
    )

    assert result.verdict == "conflicted"


def test_blocking_issue_cannot_be_overridden_by_support(claim) -> None:
    result = merge_verdict(
        claim=claim,
        rules=RuleCheckResult(
            eligible_evidence_ids=["ev-support"],
            issues=[
                VerificationIssue(
                    code="source_independence_insufficient",
                    severity="blocking",
                    message="来源不足",
                )
            ],
        ),
        assessments=[
            EvidenceAssessment(
                evidence_id="ev-support",
                relation="supports",
                reason="支持",
            )
        ],
        provider_error=None,
    )

    assert result.verdict == "partially_supported"
    assert result.verdict != "verified"


def test_provider_failure_never_verifies(claim) -> None:
    result = merge_verdict(
        claim=claim,
        rules=RuleCheckResult(eligible_evidence_ids=["ev-support"]),
        assessments=[],
        provider_error="TimeoutError",
    )

    assert result.verdict in {"partially_supported", "unsupported"}


def test_forced_out_of_range_bypasses_provider(claim) -> None:
    class NeverCalledModel:
        calls = 0

        async def ainvoke(self, _messages):
            self.calls += 1
            return SimpleNamespace(content="{}", usage_metadata={})

    model = NeverCalledModel()
    agent = VerifierAgent(model)
    rules = {
        claim.claim_id: RuleCheckResult(
            forced_verdict="out_of_range",
            issues=[
                VerificationIssue(
                    code="claim_out_of_range",
                    severity="blocking",
                    message="越界",
                )
            ],
        )
    }

    async def run():
        return await agent.averify_with_rules(
            [claim], {}, {}, None, rules
        )

    results, usage = __import__("asyncio").run(run())
    assert results[claim.claim_id].verdict == "out_of_range"
    assert model.calls == 0
    assert usage.total_tokens == 0


@pytest.mark.anyio
async def test_invalid_json_retries_once_and_returns_safe_result(claim) -> None:
    class BadModel:
        calls = 0

        async def ainvoke(self, _messages):
            self.calls += 1
            return SimpleNamespace(
                content="bad",
                usage_metadata={
                    "input_tokens": 1,
                    "output_tokens": 1,
                    "total_tokens": 2,
                },
            )

    model = BadModel()
    agent = VerifierAgent(model)
    results, usage = await agent.averify_with_rules(
        [claim],
        {},
        {},
        None,
        {
            claim.claim_id: RuleCheckResult(
                eligible_evidence_ids=["ev-support"]
            )
        },
    )

    assert model.calls == 2
    assert results[claim.claim_id].verdict != "verified"
    assert usage.total_tokens == 4
    assert results[claim.claim_id].verified_at <= datetime.now(UTC)

