from langchain_core.messages import AIMessage, HumanMessage, ToolMessage


def test_recorder_keeps_unknown_and_invalid_requests_without_answer_text():
    from deeptrace.eval.trajectory import TrajectoryRecorder

    recorder = TrajectoryRecorder()
    response = AIMessage(
        content="private-model-content-not-for-export",
        tool_calls=[{"name": "unknown_tool", "args": {"query": "x"}, "id": "call-a"}],
        invalid_tool_calls=[
            {"name": "fetch_page", "args": "broken", "id": "bad", "error": "invalid"}
        ],
    )
    recorder.record_model(
        "researcher", [HumanMessage(content="当前研究分支：topic A")], response
    )
    snapshot = recorder.snapshot()
    turn = snapshot["model_turns"][0]
    assert turn["branch"] == "topic A"
    assert turn["tool_calls"][0]["name"] == "unknown_tool"
    assert turn["invalid_tool_calls"][0]["args"] == "broken"
    assert "private-model-content-not-for-export" not in str(snapshot)
    snapshot["model_turns"].clear()
    assert len(recorder.snapshot()["model_turns"]) == 1


def test_export_does_not_derive_reference_calls_from_agent_output():
    from deeptrace.eval import Corpus, CorpusDocument, EvalQuestion
    from deeptrace.eval.runner import RunRecord
    from deeptrace.eval.trajectory import build_tool_eval_export

    question = EvalQuestion(
        id="q",
        question="task",
        reference_tool_calls=[
            {"name": "fetch_page", "args": {"url": "https://example.com/a"}}
        ],
    )
    record = RunRecord(
        question_id="q",
        mode="workflow",
        question="task",
        run_id="r",
        status="completed",
        termination_reason="completed",
        answered=True,
    )
    corpus = Corpus(
        [CorpusDocument(doc_id="d", url="https://example.com/a", title="a", body="a")]
    )
    payload = build_tool_eval_export(
        [record], [question], corpus, model_kind="scripted"
    )
    assert payload["samples"][0]["reference_tool_calls"] == [
        {"name": "fetch_page", "args": {"url": "https://example.com/a"}}
    ]
    assert payload["samples"][0]["trajectory"]["model_turns"] == []


def test_observations_keep_pre_gateway_rejections_without_body_or_duplicates():
    import json

    from deeptrace.eval.trajectory import TrajectoryRecorder

    recorder = TrajectoryRecorder()
    messages = [
        HumanMessage(content="当前研究分支：branch"),
        ToolMessage(
            tool_call_id="denied",
            content=json.dumps(
                {
                    "ok": False,
                    "tool": "unknown_tool",
                    "error_code": "tool_not_registered",
                    "error_category": "policy",
                    "preview": "private-page-body",
                }
            ),
        ),
    ]
    recorder.record_observations("researcher", messages)
    recorder.record_observations("researcher", messages)
    observations = recorder.snapshot()["tool_observations"]
    assert len(observations) == 1
    assert observations[0]["error_code"] == "tool_not_registered"
    assert observations[0]["tool_call_id"] == "denied"
    assert "private-page-body" not in str(recorder.snapshot())


def test_gateway_exception_is_recorded_and_still_propagates():
    import asyncio

    import pytest

    from deeptrace.domain import ResearchMode, ToolName, ToolRequest
    from deeptrace.eval.env import CountingToolGateway
    from deeptrace.eval.trajectory import TrajectoryRecorder
    from deeptrace.tools.policy import CallerRole, ToolCaller

    class BrokenGateway:
        async def execute(self, **kwargs):
            raise RuntimeError("private-gateway-error")

    recorder = TrajectoryRecorder()
    gateway = CountingToolGateway(BrokenGateway(), recorder)
    request = ToolRequest(
        request_id="req",
        run_id="run",
        thread_id="thread",
        call_id="call",
        tool=ToolName.SEARCH_WEB,
        arguments={"query": "test"},
    )
    caller = ToolCaller(
        caller_id="caller", role=CallerRole.WORKFLOW_GRAPH, mode=ResearchMode.WORKFLOW
    )
    with pytest.raises(RuntimeError):
        asyncio.run(gateway.execute(caller=caller, request=request))
    result = recorder.snapshot()["tool_executions"][0]
    assert result["ok"] is False
    assert result["exception_type"] == "RuntimeError"
    assert result["call_id"] == "call"
    assert "private-gateway-error" not in str(result)
