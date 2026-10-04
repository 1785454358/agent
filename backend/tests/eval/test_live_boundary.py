"""Live evaluation stays bounded while permitting explicit paired designs."""

from dataclasses import replace

import pytest
from harness.test_agent_invariants import Model, assert_pairs, call, task
from langchain_core.messages import AIMessage
from strategies.fixtures import build_gateway_fixture

from deeptrace.eval.env import CountingToolGateway
from deeptrace.eval.telemetry import RequestCounter
from deeptrace.eval.trajectory import TrajectoryRecorder
from deeptrace.harness.agent_executor import build_research_agent_graph


@pytest.mark.asyncio
async def test_counting_gateway_limit_is_budget_not_internal_tool_error():
    fixture = build_gateway_fixture()
    gateway = CountingToolGateway(
        fixture.context.tool_gateway,
        TrajectoryRecorder(),
        counter=RequestCounter(1, used=1),
    )
    model = Model(
        AIMessage(
            content="", tool_calls=[call("search_web", {"query": "official docs"}, "s")]
        )
    )
    result = await build_research_agent_graph(max_iterations=1).ainvoke(
        {"topic_input": task()},
        context=replace(fixture.context, model_gateway=model, tool_gateway=gateway),
    )
    assert result["outcome"].agent_outcome.stop_reason == "budget_exhausted"
    assert gateway.calls == []
    assert_pairs(result["messages"])


def test_explicit_live_question_list_modes_and_repeats_reach_preflight(monkeypatch):
    from deeptrace.config import Settings
    from deeptrace.eval import __main__ as cli
    from tests.eval.test_experiment import assets

    class PreflightReached(Exception):
        pass

    def stop_before_credentials():
        raise PreflightReached

    questions, _ = assets()
    monkeypatch.setattr(
        cli,
        "load_questions",
        lambda _: [questions[0], questions[0].model_copy(update={"id": "q2"})],
    )
    monkeypatch.setattr(Settings, "from_env", stop_before_credentials)
    with pytest.raises(PreflightReached):
        cli.main(
            [
                "--dataset",
                "explicit.jsonl",
                "--model",
                "real",
                "--modes",
                "plan_execute",
                "--repeats",
                "2",
                "--out",
                "unused",
                "--max-batch-model-calls",
                "160",
                "--max-batch-provider-attempts",
                "320",
            ],
            live_web=True,
        )


def test_live_report_does_not_claim_frozen_corpus():
    from deeptrace.eval.report import render_markdown
    from deeptrace.eval.scoring import ScoreReport

    report = render_markdown(
        ScoreReport(runs=0, questions=0, modes=[]), tools_backend="live_web"
    )
    assert "live web" in report
    assert "offline corpus" not in report
    assert "frozen local corpus" not in report
