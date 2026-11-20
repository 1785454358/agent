import json

import pytest
from langchain_core.messages import AIMessage
from types import SimpleNamespace


@pytest.mark.asyncio
async def test_supported_label_cannot_release_wrong_number_and_unchecked_claim():
    from deeptrace.responses.claim_audit import audit_claims
    class Auditor:
        async def invoke(self, **kwargs):
            return AIMessage(content=json.dumps({"checks":[
                {"id":"c1","status":"supported","reason":"claimed supported",
                 "supports":[{"ref":"[1]","quote":"Model-A achieved a score of 71.2 in this experiment."}]},
                {"id":"c2","status":"supported","reason":"same value",
                 "supports":[{"ref":"[1]","quote":"Model-A achieved a score of 71.2 in this experiment."}]}],
                "unanswered_points":[]}))
    result = await audit_claims(SimpleNamespace(model_gateway=Auditor()),question="Compare scores",
        content="Model-A achieved 99.9 [1].\nModel-A achieved 71.2 [1].\nModel-A always outperforms competitors [1].",
        sources=["[1] Model-A achieved a score of 71.2 in this experiment."], input_budget=20000)
    assert "99.9" not in result.content
    assert "always" not in result.content
    assert "71.2" in result.content
    assert result.rejected == 2


@pytest.mark.asyncio
async def test_finite_experiment_cannot_support_universal_claim_or_quote_from_other_source():
    from deeptrace.responses.claim_audit import audit_claims
    class Auditor:
        async def invoke(self, **kwargs):
            return AIMessage(content=json.dumps({"checks":[
                {"id":"c1","status":"supported","reason":"an experiment",
                 "supports":[{"ref":"[1]","quote":"Model-A improved on this benchmark."}]},
                {"id":"c2","status":"supported","reason":"wrong source",
                 "supports":[{"ref":"[2]","quote":"Model-B achieved 83.2 on Benchmark-B."}]}],"unanswered_points":[]}))
    result=await audit_claims(SimpleNamespace(model_gateway=Auditor()),question="Compare",
        content="Model-A always improves on all benchmarks [1].\nModel-B achieved 83.2 [1].",
        sources=["[1] Model-A improved on this benchmark.","[2] Model-B achieved 83.2 on Benchmark-B."], input_budget=20000)
    assert "always improves" not in result.content
    assert "83.2" not in result.content


def test_claim_selection_skips_code_and_program_generated_tables():
    from deeptrace.responses.claim_audit import select_claims
    text="```text\nAlways use 99 samples [1].\n```\n| Model | Score |\n|---|---|\n| A | 99.9 [1] |\n模型A必然优于模型B [1]。"
    claims=select_claims(text)
    assert len(claims)==1
    assert "必然" in claims[0].text
