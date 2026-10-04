import pytest

from deeptrace.domain import ResearchMode
from deeptrace.eval import Corpus, CorpusDocument, EvalQuestion, ScriptedResearchModel
from deeptrace.eval.runner import run_matrix


@pytest.mark.asyncio
async def test_actual_baseline_is_invariant_to_scoring_reference_changes():
    corpus = Corpus(
        [
            CorpusDocument(
                doc_id="d",
                url="https://example.org/d",
                title="checkpoint",
                body="checkpoint saves graph state",
            )
        ]
    )
    results = []
    for reference in ("GOLD_CANARY_ALPHA", "GOLD_CANARY_BETA"):
        question = EvalQuestion(
            id="q",
            question="checkpoint",
            gold_answer=reference,
            gold_urls=[f"https://reference-only.example/{reference}"],
        )
        records = await run_matrix(
            [question],
            corpus,
            model_factory=ScriptedResearchModel,
            modes=(ResearchMode.WORKFLOW,),
            include_baseline=True,
        )
        results.append(next(r for r in records if r.mode == "baseline"))
    assert results[0].answer == results[1].answer
    assert results[0].trajectory == results[1].trajectory
    assert results[0].evidence == results[1].evidence
    assert "GOLD_CANARY" not in str(results[0].trajectory)


@pytest.mark.asyncio
async def test_both_systems_deliver_tail_under_same_cap_without_gold_leakage():
    fact = "Checkpoint recovery does not replay external side effects in v2."
    body = "unrelated introduction\n\n" * 800 + "## Recovery limits\n\n" + fact
    corpus = Corpus(
        [
            CorpusDocument(
                doc_id="d",
                url="https://example.org/d",
                title="checkpoint recovery",
                body=body,
            )
        ]
    )
    inputs = []
    for gold in ("GOLD_CANARY_ALPHA", "GOLD_CANARY_BETA"):
        records = await run_matrix(
            [
                EvalQuestion(
                    id="q",
                    question="Checkpoint recovery limits in v2?",
                    gold_answer=gold,
                    gold_urls=[f"https://gold.example/{gold}"],
                )
            ],
            corpus,
            model_factory=ScriptedResearchModel,
            modes=(ResearchMode.WORKFLOW,),
            include_baseline=True,
        )
        excerpts = []
        for record in records:
            assert record.evidence[0]["body"] == body
            messages = record.trajectory["model_messages"]
            responder = next(turn for turn in messages if turn["role"] == "responder")
            prompt = responder["messages"][-1]["content"]
            assert fact in prompt
            assert "GOLD_CANARY" not in str(messages)
            excerpts.append(
                prompt.split("正文摘录：\n", 1)[1].split("\n只输出 JSON", 1)[0]
            )
        assert len(excerpts) == 2
        # Same corpus/cap, but Harness additionally prioritizes accepted supports.
        # Exact excerpts intentionally differ; neither may depend on the oracle.
        assert all(len(excerpt) <= 3500 for excerpt in excerpts)
        inputs.append(excerpts)
    assert inputs[0] == inputs[1]


@pytest.mark.asyncio
async def test_fixed_baseline_uses_governed_tools_without_planning_or_gold():
    corpus = Corpus(
        [
            CorpusDocument(
                doc_id=f"d{i}",
                url=f"https://example.org/{i}",
                title="checkpoint",
                body=f"checkpoint fact {i}",
            )
            for i in range(5)
        ]
    )
    question = EvalQuestion(
        id="q", question="checkpoint", gold_answer="GOLD_SECRET_SENTINEL"
    )
    records = await run_matrix(
        [question],
        corpus,
        model_factory=ScriptedResearchModel,
        modes=(ResearchMode.WORKFLOW,),
        include_baseline=True,
    )
    baseline = next(r for r in records if r.mode == "baseline")
    assert baseline.status == "completed"
    assert baseline.fetched_pages == 3
    assert baseline.tool_calls == 4
    assert baseline.cited_evidence_ids
    assert baseline.evidence_urls == [
        "https://example.org/0",
        "https://example.org/1",
        "https://example.org/2",
    ]
    assert "GOLD_SECRET_SENTINEL" not in str(baseline.trajectory)
    assert not {turn["role"] for turn in baseline.trajectory["model_turns"]} & {
        "planner",
        "researcher",
        "evaluator",
    }
    requests = baseline.trajectory["tool_executions"]
    assert requests[0]["arguments"] == {"query": "checkpoint", "limit": 5}
    assert all(row["ok"] for row in requests)


@pytest.mark.asyncio
async def test_baseline_with_no_search_hits_is_partial_not_false_success():
    corpus = Corpus(
        [
            CorpusDocument(
                doc_id="d",
                url="https://example.org/a",
                title="unrelated",
                body="unrelated",
            )
        ]
    )
    records = await run_matrix(
        [EvalQuestion(id="q", question="checkpoint")],
        corpus,
        model_factory=ScriptedResearchModel,
        modes=(ResearchMode.WORKFLOW,),
        include_baseline=True,
    )
    baseline = next(r for r in records if r.mode == "baseline")
    assert baseline.status == "partial"
    assert baseline.termination_reason == "no_sources"
    assert baseline.fetched_pages == 0
    assert not baseline.cited_evidence_ids


def test_cli_baseline_is_an_identified_resumable_system(tmp_path):
    import json

    from deeptrace.eval.__main__ import main

    args = ["--modes", "workflow", "--include-baseline", "--out", str(tmp_path)]
    assert main(args) == 0
    first = (tmp_path / "records.json").read_bytes()
    assert {r["mode"] for r in json.loads(first)} == {"workflow", "baseline"}
    assert main([*args, "--resume"]) == 0
    assert (tmp_path / "records.json").read_bytes() == first
